"""
Flask API for Kanban Board Management System
Connects to MySQL database and provides REST APIs for projects, tickets, and users management.
"""

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import json
import os
import uuid
from dotenv import load_dotenv
from datetime import datetime
from rag.rag_generator import FALLBACK, generate_answer, sources_for_context, stream_answer
from rag.rag_retriever import retrieve_tickets
from rag.rag_updator import synchronize_ticket



app = Flask(__name__)
CORS(app)

load_dotenv()  # Load environment variables from .env file

# MySQL Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'workflow'),
    'port': int(os.getenv('DB_PORT', 3306))
}


def get_db_connection():
    """Create and return a MySQL database connection."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        print("Successfully connected to MySQL database")
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None


def execute_query(query, params, fetch=False):
    """
    Execute a SQL query with proper error handling and transaction management.
    
    Args:
        query: SQL query string
        params: Query parameters (list or tuple)
        fetch: If True, fetch and return results; if False, commit and return affected rows
    
    Returns:
        Tuple of (success, result/error_message, affected_rows)
    """
    connection = get_db_connection()
    if not connection:
        return False, "Database connection failed", 0
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        
        if fetch:
            results = cursor.fetchall()
            cursor.close()
            connection.close()
            return True, results, len(results)
        else:
            connection.commit()
            affected_rows = cursor.rowcount
            cursor.close()
            connection.close()
            return True, None, affected_rows
    
    except Error as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return False, str(e), 0

    except Exception as e:
        connection.rollback()
        cursor.close()
        connection.close()
        return False, str(e), 0


def execute_insert(query, params):
    """Execute an insert and return the generated primary-key value."""
    connection = get_db_connection()
    if not connection:
        return False, "Database connection failed", 0

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        generated_id = cursor.lastrowid
        connection.commit()
        cursor.close()
        connection.close()
        return True, None, generated_id
    except Error as error:
        connection.rollback()
        if cursor:
            cursor.close()
        connection.close()
        return False, str(error), 0
    except Exception as error:
        connection.rollback()
        if cursor:
            cursor.close()
        connection.close()
        return False, str(error), 0


def get_ticket_for_rag(ticket_id):
    """Load the complete saved ticket view used by the retrieval index."""
    query = """
        SELECT
            p.id AS project_id, p.name AS project_name,
            p.description AS project_description, p.created_at AS project_created_at,
            project_creator.user_name AS project_created_by,
            t.id AS ticket_id, t.title AS ticket_title,
            t.description AS ticket_description, t.created_at AS ticket_created_at,
            ticket_creator.user_name AS ticket_created_by, t.updated_at AS ticket_updated_at,
            ticket_updater.user_name AS ticket_updated_by,
            assignee.user_name AS assigned_user_name, t.due_date AS ticket_due_date,
            s.name AS status_name
        FROM projects AS p
        JOIN tickets AS t ON p.id = t.project_id
        LEFT JOIN status AS s ON s.id = t.status_id
        LEFT JOIN users AS project_creator ON p.created_by = project_creator.user_id
        LEFT JOIN users AS ticket_creator ON t.created_by = ticket_creator.user_id
        LEFT JOIN users AS ticket_updater ON t.updated_by = ticket_updater.user_id
        LEFT JOIN users AS assignee ON t.assigned_user_id = assignee.user_id
        WHERE t.id = %s
    """
    success, tickets, _ = execute_query(query, [ticket_id], fetch=True)
    return tickets[0] if success and tickets else None


# ==================== Project Endpoints ====================

@app.route('/create_project', methods=['POST'])
def create_project():
    """
    Create a new project with statuses and users in a single transaction.
    
    Request JSON:
    {
        "project_name": "Project Name",
        "description": "Project Description (optional)",
        "status": ["New", "In Progress", "Done"],
        "users": [1, 2, 3]
    }
    
    Response:
    {
        "success": true,
        "message": "Project created successfully",
        "project_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'project_name' not in data:
            return jsonify({'success': False, 'message': 'project_name is required'}), 400
        
        project_name = data.get('project_name', '').strip()
        project_description = data.get('description', '').strip() or None
        statuses = data.get('status', [])
        user_ids = data.get('users', [])
        created_by = data.get('created_by', 1)
        
        if not project_name:
            return jsonify({'success': False, 'message': 'Project name cannot be empty'}), 400
        
        if not isinstance(statuses, list) or len(statuses) == 0:
            return jsonify({'success': False, 'message': 'At least one status is required'}), 400
        
        if not isinstance(user_ids, list):
            return jsonify({'success': False, 'message': 'users must be an array'}), 400
        
        # Get database connection
        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Database connection failed'}), 500
        
        try:
            cursor = connection.cursor()
            
            # Start transaction
            cursor.execute("START TRANSACTION")
            
            # 1. Insert project into projects table
            insert_project_query = """
                INSERT INTO projects (name, description, created_by, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
            """
            project_params = (project_name, project_description, created_by)
            cursor.execute(insert_project_query, project_params)
            
            # Get the auto-increment project_id
            cursor.execute("SELECT LAST_INSERT_ID()")
            project_id = cursor.fetchone()[0]
            
            # 2. Insert statuses into status table
            insert_status_query = """
                INSERT INTO status (project_id, name, description, sort_order, is_active, created_at)
                VALUES (%s, %s, %s, %s, TRUE, NOW())
            """
            for idx, status_name in enumerate(statuses, 1):
                status_name = status_name.strip()
                if status_name:
                    status_params = (project_id, status_name, None, idx)
                    cursor.execute(insert_status_query, status_params)
            
            # 3. Insert project users into project_users table
            if user_ids:
                insert_project_user_query = """
                    INSERT INTO project_users (user_id, project_id, created_by, created_at)
                    VALUES (%s, %s, %s, NOW())
                """
                for user_id in user_ids:
                    if isinstance(user_id, (int, str)):
                        try:
                            user_id_int = int(user_id)
                            user_params = (user_id_int, project_id, created_by)
                            cursor.execute(insert_project_user_query, user_params)
                        except (ValueError, TypeError):
                            print(f"Warning: Invalid user_id {user_id}, skipping")
            
            # Commit transaction
            connection.commit()
            cursor.close()
            connection.close()
                        
            connection.commit()
            
            return jsonify({
                'success': True,
                'message': 'Project created successfully',
                'project_id': project_id
            }), 201
        
        except Error as e:
            connection.rollback()
            cursor.close()
            connection.close()
            print(f"Database error: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Failed to create project: {str(e)}'
            }), 500
        
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            print(f"Unexpected error: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Unexpected error: {str(e)}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/get_projects', methods=['GET'])
def get_projects():
    """
    Get all projects.
    
    Response:
    {
        "success": true,
        "projects": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Project 1",
                "description": "Description",
                "created_by": 1,
                "created_at": "2024-01-01T10:00:00"
            }
        ]
    }
    """
    try:
        query = """
            SELECT id, name, description, created_by, created_at, updated_at
            FROM projects
            ORDER BY created_at DESC
        """
        
        success, projects, _ = execute_query(query, [], fetch=True)
        
        if success:
            return jsonify({
                'success': True,
                'projects': projects
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch projects: {projects}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


# ==================== Ticket Endpoints ====================

@app.route('/create_ticket', methods=['POST'])
def create_ticket():
    try:
        data = request.get_json()

        required_fields = ['project_id', 'title', 'status_id']

        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'success': False,
                'message': f'Required fields missing: {", ".join(required_fields)}'
            }), 400

        project_id = data.get('project_id')
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        status_id = data.get('status_id')
        assigned_user_id = data.get('assigned_user_id')
        created_by = data.get('created_by')
        due_date = data.get('due_date')

        if not title:
            return jsonify({
                'success': False,
                'message': 'Ticket title cannot be empty'
            }), 400

        # Convert ISO 8601 datetime to MySQL DATETIME
        if due_date:
            try:
                due_date = datetime.fromisoformat(
                    due_date.replace('Z', '+00:00')
                ).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid due_date format. Expected ISO 8601 datetime.'
                }), 400

        query = """
            INSERT INTO tickets (
                project_id,
                title,
                description,
                status_id,
                assigned_user_id,
                created_by,
                created_at,
                updated_at,
                due_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
        """

        params = (
            project_id,
            title,
            description,
            status_id,
            assigned_user_id,
            created_by,
            due_date
        )

        success, error_msg, ticket_id = execute_insert(
            query,
            params,
        )

        if success:
            try:
                ticket = get_ticket_for_rag(ticket_id)
                if ticket:
                    app.logger.info(
                        "Create-ticket embedding started: ticket_id=%s project_id=%s",
                        ticket_id,
                        ticket.get('project_id'),
                    )
                    chunk_count = synchronize_ticket(ticket)
                    app.logger.info(
                        "Create-ticket embedding completed: ticket_id=%s project_id=%s chunks=%s store=chroma",
                        ticket_id,
                        ticket.get('project_id'),
                        chunk_count,
                    )
                else:
                    app.logger.warning(
                        "Create-ticket embedding skipped: ticket_id=%s reason=ticket_not_found",
                        ticket_id,
                    )
            except Exception:
                app.logger.exception(
                    "Create-ticket embedding failed: ticket_id=%s store=chroma",
                    ticket_id,
                )

            return jsonify({
                'success': True,
                'message': 'Ticket created successfully',
                'ticket_id': ticket_id
            }), 201

        return jsonify({
            'success': False,
            'message': f'Failed to create ticket: {error_msg}'
        }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/get_tickets/<project_id>', methods=['GET'])
def get_tickets(project_id):
    """
    Get all tickets for a specific project.
    
    Response:
    {
        "success": true,
        "tickets": [
            {
                "id": 1,
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Ticket 1",
                "description": "Description",
                "status_id": 1,
                "assigned_user_id": 1,
                "created_by": 1,
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T10:00:00",
                "due_date": "2024-12-31T23:59:59"
            }
        ]
    }
    """
    try:
        query = """
            SELECT id, project_id, title, description, status_id, assigned_user_id,
                   created_by, created_at, updated_at, due_date
            FROM tickets
            WHERE project_id = %s
            ORDER BY created_at DESC
        """
        
        success, tickets, _ = execute_query(query, [project_id], fetch=True)
        
        if success:
            return jsonify({
                'success': True,
                'tickets': tickets
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch tickets: {tickets}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/update_status', methods=['PUT'])
def update_status():
    """
    Update ticket status (e.g., drag and drop to different column).
    
    Request JSON:
    {
        "ticket_id": 1,
        "status_id": 2
    }
    
    Response:
    {
        "success": true,
        "message": "Ticket status updated successfully"
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'ticket_id' not in data or 'status_id' not in data:
            return jsonify({
                'success': False,
                'message': 'ticket_id and status_id are required'
            }), 400
        
        ticket_id = data.get('ticket_id')
        status_id = data.get('status_id')
        
        # Update ticket status
        query = """
            UPDATE tickets
            SET status_id = %s, updated_at = NOW()
            WHERE id = %s
        """
        params = (status_id, ticket_id)
        
        success, error_msg, affected_rows = execute_query(query, params, fetch=False)
        
        if success:
            if affected_rows > 0:
                try:
                    ticket = get_ticket_for_rag(ticket_id)
                    if ticket:
                        synchronize_ticket(ticket)
                except Exception:
                    app.logger.exception("Ticket %s status changed but could not be indexed", ticket_id)
                return jsonify({
                    'success': True,
                    'message': 'Ticket status updated successfully'
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'Ticket not found'
                }), 404
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to update ticket status: {error_msg}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500



@app.route('/edit_ticket', methods=['PUT'])
def edit_ticket():
    """
    Edit an existing ticket.

    Request JSON:
    {
        "ticket_id": 1,
        "title": "Updated Title",
        "description": "Updated Description",
        "status_id": 2,
        "assigned_user_id": 2,
        "due_date": "2026-09-30T00:00:00.000Z",
        "updated_by": 1
    }
    """

    try:
        data = request.get_json()

        # Validate request
        if not data or 'ticket_id' not in data:
            return jsonify({
                'success': False,
                'message': 'ticket_id is required'
            }), 400

        ticket_id = data.get('ticket_id')

        update_fields = []
        params = []

        # Title
        if 'title' in data:
            title = data.get('title')

            if title is not None:
                title = title.strip()

            update_fields.append('title = %s')
            params.append(title)

        # Description
        if 'description' in data:
            description = data.get('description')

            if description is not None:
                description = description.strip()

            update_fields.append('description = %s')
            params.append(description)

        # Status
        if 'status_id' in data:
            update_fields.append('status_id = %s')
            params.append(data.get('status_id'))

        # Assigned User
        if 'assigned_user_id' in data:
            update_fields.append('assigned_user_id = %s')
            params.append(data.get('assigned_user_id'))

        # Due Date
        if 'due_date' in data:
            due_date = data.get('due_date')

            if due_date:
                try:
                    # Angular ISO date:
                    # 2026-09-30T00:00:00.000Z
                    #
                    # Convert to MySQL DATETIME:
                    # 2026-09-30 00:00:00

                    due_date = datetime.fromisoformat(
                        due_date.replace('Z', '+00:00')
                    ).strftime('%Y-%m-%d %H:%M:%S')

                except (ValueError, TypeError):
                    return jsonify({
                        'success': False,
                        'message': (
                            'Invalid due_date format. '
                            'Expected ISO 8601 datetime.'
                        )
                    }), 400
            else:
                # Allow clearing the due date
                due_date = None

            update_fields.append('due_date = %s')
            params.append(due_date)

        # Updated By
        if 'updated_by' in data:
            update_fields.append('updated_by = %s')
            params.append(data.get('updated_by'))

        # No fields to update
        if not update_fields:
            return jsonify({
                'success': False,
                'message': 'No fields to update'
            }), 400

        # Always update updated_at
        update_fields.append('updated_at = NOW()')

        # WHERE parameter
        params.append(ticket_id)

        query = f"""
            UPDATE tickets
            SET {', '.join(update_fields)}
            WHERE id = %s
        """

        success, error_msg, affected_rows = execute_query(
            query,
            params,
            fetch=False
        )

        if success:

            if affected_rows > 0:
                try:
                    ticket = get_ticket_for_rag(ticket_id)
                    if ticket:
                        synchronize_ticket(ticket)
                except Exception:
                    app.logger.exception("Ticket %s was updated but could not be indexed", ticket_id)
                return jsonify({
                    'success': True,
                    'message': 'Ticket updated successfully'
                }), 200

            return jsonify({
                'success': False,
                'message': 'Ticket not found'
            }), 404

        return jsonify({
            'success': False,
            'message': f'Failed to update ticket: {error_msg}'
        }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/question', methods=['POST'])
def question():
    """Answer a ticket question using only retrieved ticket context."""
    data = request.get_json(silent=True) or {}
    question_text = data.get('question', '')
    context = retrieve_tickets(
        question_text,
        project_id=data.get('project_id'),
        ticket_id=data.get('ticket_id'),
        k=data.get('k', 5),
    )
    result = generate_answer(question_text, context)
    return jsonify({
        'success': True,
        'answer': result['answer'],
        'sources': result['sources'],
    }), 200


@app.route('/api/rag/chat', methods=['POST'])
def rag_chat():
    """Stream a grounded ticket answer and its sources as server-sent events."""
    data = request.get_json(silent=True)
    message = data.get('message', '') if isinstance(data, dict) else ''
    raw_history = data.get('history', []) if isinstance(data, dict) else []
    if not isinstance(message, str) or not message.strip():
        return jsonify({
            'success': False,
            'message': 'message is required and cannot be empty'
        }), 400

    question_text = message.strip()
    history = []
    if isinstance(raw_history, list):
        for item in raw_history[-6:]:
            if not isinstance(item, dict):
                continue
            role = item.get('role')
            content = item.get('content')
            if role in {'user', 'assistant'} and isinstance(content, str) and content.strip():
                history.append({'role': role, 'content': content.strip()[:2000]})
    request_id = str(uuid.uuid4())

    def event_stream():
        def event(name, payload):
            return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield event('start', {'request_id': request_id})
        try:
            retrieval_query = question_text
            if history:
                previous_questions = '\n'.join(
                    item['content'] for item in history if item['role'] == 'user'
                )
                retrieval_query = f'{previous_questions}\n{question_text}'
            context = retrieve_tickets(retrieval_query, k=5)
            sources = sources_for_context(context)
            answer_parts = []
            for text in stream_answer(question_text, context, history):
                answer_parts.append(text)
                yield event('chunk', {'text': text})
            answer = ''.join(answer_parts).strip() or FALLBACK
            yield event('complete', {'answer': answer, 'sources': sources})
        except GeneratorExit:
            app.logger.info('RAG stream %s closed by client', request_id)
            raise
        except Exception:
            app.logger.exception('RAG stream %s failed', request_id)
            yield event('error', {'message': 'Unable to generate a response.'})

    return Response(
        stream_with_context(event_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )


# ==================== Status Endpoints ====================

@app.route('/create_status', methods=['POST'])
def create_status():
    """
    Create a new status for a project.
    
    Request JSON:
    {
        "project_id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "In Progress",
        "description": "Work in progress",
        "sort_order": 2
    }
    
    Response:
    {
        "success": true,
        "message": "Status created successfully",
        "status_id": 2
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'project_id' not in data or 'name' not in data:
            return jsonify({
                'success': False,
                'message': 'project_id and name are required'
            }), 400
        
        project_id = data.get('project_id')
        status_name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        sort_order = data.get('sort_order', 0)
        
        if not status_name:
            return jsonify({'success': False, 'message': 'Status name cannot be empty'}), 400
        
        # Insert status into database
        query = """
            INSERT INTO status (project_id, name, description, sort_order, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """
        params = (project_id, status_name, description, sort_order)
        
        success, error_msg, _ = execute_query(query, params, fetch=False)
        
        if success:
            # Get the last inserted status ID
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT LAST_INSERT_ID()")
            status_id = cursor.fetchone()[0]
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'message': 'Status created successfully',
                'status_id': status_id
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to create status: {error_msg}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/get_statuses/<project_id>', methods=['GET'])
def get_statuses(project_id):
    """
    Get all statuses for a specific project.
    
    Response:
    {
        "success": true,
        "statuses": [
            {
                "id": 1,
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Open",
                "description": "New tickets",
                "sort_order": 1,
                "is_active": true,
                "created_at": "2024-01-01T10:00:00"
            }
        ]
    }
    """
    try:
        query = """
            SELECT id, project_id, name, description, sort_order, is_active, created_at
            FROM status
            WHERE project_id = %s AND is_active = TRUE
            ORDER BY sort_order ASC
        """
        
        success, statuses, _ = execute_query(query, [project_id], fetch=True)
        
        if success:
            return jsonify({
                'success': True,
                'statuses': statuses
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch statuses: {statuses}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


# ==================== User Endpoints ====================

@app.route('/create_user', methods=['POST'])
def create_user():
    """
    Create a new user.
    
    Request JSON:
    {
        "user_name": "John Doe",
        "email": "john@example.com",
        "created_by": 1
    }
    
    Response:
    {
        "success": true,
        "message": "User created successfully",
        "user_id": 1
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'user_name' not in data:
            return jsonify({
                'success': False,
                'message': 'user_name is required'
            }), 400
        
        user_name = data.get('user_name', '').strip()
        email = data.get('email', '').strip()
        created_by = data.get('created_by')
        
        if not user_name:
            return jsonify({'success': False, 'message': 'User name cannot be empty'}), 400
        
        # Insert user into database
        query = """
            INSERT INTO users (user_name, email, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
        """
        params = (user_name, email or None, created_by)
        
        success, error_msg, _ = execute_query(query, params, fetch=False)
        
        if success:
            # Get the last inserted user ID
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT LAST_INSERT_ID()")
            user_id = cursor.fetchone()[0]
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'message': 'User created successfully',
                'user_id': user_id
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to create user: {error_msg}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/get_users', methods=['GET'])
def get_users():
    """
    Get all active users.
    
    Response:
    {
        "success": true,
        "users": [
            {
                "user_id": 1,
                "user_name": "John Doe",
                "email": "john@example.com",
                "is_active": true,
                "created_at": "2024-01-01T10:00:00"
            }
        ]
    }
    """
    try:
        query = """
            SELECT user_id, user_name, email, is_active, created_at
            FROM users
            WHERE is_active = TRUE
            ORDER BY user_name ASC
        """
        
        success, users, _ = execute_query(query, [], fetch=True)
        
        if success:
            return jsonify({
                'success': True,
                'users': users
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch users: {users}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


# ==================== Project Users Endpoints ====================

@app.route('/add_project_users', methods=['POST'])
def add_project_users():
    """
    Add users to a project.
    
    Request JSON:
    {
        "project_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_ids": [1, 2, 3],
        "added_by": 1
    }
    
    Response:
    {
        "success": true,
        "message": "Project users added successfully",
        "added_count": 3
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data or 'project_id' not in data or 'user_ids' not in data:
            return jsonify({
                'success': False,
                'message': 'project_id and user_ids are required'
            }), 400
        
        project_id = data.get('project_id')
        user_ids = data.get('user_ids', [])
        added_by = data.get('added_by', 1)
        
        if not isinstance(user_ids, list) or len(user_ids) == 0:
            return jsonify({
                'success': False,
                'message': 'user_ids must be a non-empty array'
            }), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'message': 'Database connection failed'
            }), 500
        
        try:
            cursor = connection.cursor()
            added_count = 0
            
            for user_id in user_ids:
                query = """
                    INSERT INTO project_users (project_id, user_id, added_by, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE added_by = %s, created_at = NOW()
                """
                params = (project_id, user_id, added_by, added_by)
                
                try:
                    cursor.execute(query, params)
                    added_count += cursor.rowcount
                except Error as e:
                    # Skip duplicate entries, log the error
                    print(f"Warning: Could not add user {user_id} to project {project_id}: {str(e)}")
            
            connection.commit()
            cursor.close()
            connection.close()
            
            return jsonify({
                'success': True,
                'message': 'Project users added successfully',
                'added_count': added_count
            }), 201
        
        except Error as e:
            connection.rollback()
            cursor.close()
            connection.close()
            return jsonify({
                'success': False,
                'message': f'Failed to add project users: {str(e)}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


@app.route('/project_users/<project_id>', methods=['GET'])
def get_project_users(project_id):
    """
    Get all users associated with a project.
    
    Response:
    {
        "success": true,
        "users": [
            {
                "user_id": 1,
                "user_name": "John Doe",
                "email": "john@example.com",
                "is_active": true
            }
        ]
    }
    """
    try:
        query = """
            SELECT u.user_id, u.user_name, u.email, u.is_active
            FROM users u
            INNER JOIN project_users pu ON u.user_id = pu.user_id
            WHERE pu.project_id = %s
            ORDER BY u.user_name ASC
        """
        
        success, users, _ = execute_query(query, [project_id], fetch=True)
        
        if success:
            return jsonify({
                'success': True,
                'users': users
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to fetch project users: {users}'
            }), 500
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Internal server error: {str(e)}'
        }), 500


# ==================== Health Check ====================

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify the API is running.
    """
    connection = get_db_connection()
    if connection:
        connection.close()
        return jsonify({
            'status': 'healthy',
            'message': 'API is running and database connection is working'
        }), 200
    else:
        return jsonify({
            'status': 'unhealthy',
            'message': 'Database connection failed'
        }), 503


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'success': False,
        'message': 'Endpoint not found'
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors."""
    return jsonify({
        'success': False,
        'message': 'Method not allowed'
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        'success': False,
        'message': 'Internal server error'
    }), 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
