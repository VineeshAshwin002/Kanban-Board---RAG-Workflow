# Kanban Board Flask API

A simple Flask API for managing projects, tickets, users, and statuses in a Kanban board system. The API connects to a MySQL database and provides REST endpoints for CRUD operations.

## Features

✅ Create and manage projects  
✅ Create and edit tickets  
✅ Update ticket status (drag-and-drop support)  
✅ Create and manage users  
✅ Create and manage project statuses  
✅ Parameterized SQL queries (SQL injection protection)  
✅ Transaction management with rollback on errors  
✅ CORS support for cross-origin requests  
✅ Proper HTTP status codes  
✅ Error handling and validation  

## Prerequisites

- Python 3.8 or higher
- MySQL 5.7 or higher
- pip (Python package manager)

## Installation

### 1. Setup MySQL Database

Create the database and tables using the provided SQL:

```sql
CREATE DATABASE kanban_db;
USE kanban_db;

CREATE TABLE projects (
    id BINARY(16) PRIMARY KEY DEFAULT (UUID_TO_BIN(UUID())),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    user_name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by INT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    sort_order INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status_id INT,
    assigned_user_id INT,
    created_by INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by INT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    due_date DATETIME
);
```

### 2. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure Database Connection

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` with your MySQL credentials:

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=kanban_db
DB_PORT=3306
```

### 4. Run the Flask Application

```bash
python app.py
```

The API will start on `http://localhost:5000`

## API Endpoints

### Health Check

#### GET /health
Check if the API is running and database connection is working.

**Response:**
```json
{
    "status": "healthy",
    "message": "API is running and database connection is working"
}
```

### Projects

#### POST /create_project
Create a new project.

**Request:**
```json
{
    "name": "My Project",
    "description": "Project description",
    "created_by": 1
}
```

**Response:**
```json
{
    "success": true,
    "message": "Project created successfully",
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### GET /get_projects
Get all projects.

**Response:**
```json
{
    "success": true,
    "projects": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "My Project",
            "description": "Project description",
            "created_by": 1,
            "created_at": "2024-01-01T10:00:00",
            "updated_at": "2024-01-01T10:00:00"
        }
    ]
}
```

### Tickets

#### POST /create_ticket
Create a new ticket in a project.

**Request:**
```json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Implement login feature",
    "description": "Add user authentication",
    "status_id": 1,
    "assigned_user_id": 2,
    "created_by": 1,
    "due_date": "2024-12-31T23:59:59"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Ticket created successfully",
    "ticket_id": 1
}
```

#### GET /get_tickets/&lt;project_id&gt;
Get all tickets for a specific project.

**Response:**
```json
{
    "success": true,
    "tickets": [
        {
            "id": 1,
            "project_id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Implement login feature",
            "description": "Add user authentication",
            "status_id": 1,
            "assigned_user_id": 2,
            "created_by": 1,
            "created_at": "2024-01-01T10:00:00",
            "updated_at": "2024-01-01T10:00:00",
            "due_date": "2024-12-31T23:59:59"
        }
    ]
}
```

#### PUT /update_status
Update ticket status (drag-and-drop between columns).

**Request:**
```json
{
    "ticket_id": 1,
    "status_id": 2
}
```

**Response:**
```json
{
    "success": true,
    "message": "Ticket status updated successfully"
}
```

#### PUT /edit_ticket
Update an existing ticket.

**Request:**
```json
{
    "ticket_id": 1,
    "title": "Updated title",
    "description": "Updated description",
    "status_id": 2,
    "assigned_user_id": 3,
    "due_date": "2024-12-31T23:59:59",
    "updated_by": 1
}
```

**Response:**
```json
{
    "success": true,
    "message": "Ticket updated successfully"
}
```

### Statuses

#### POST /create_status
Create a new status for a project.

**Request:**
```json
{
    "project_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "In Progress",
    "description": "Work in progress",
    "sort_order": 2
}
```

**Response:**
```json
{
    "success": true,
    "message": "Status created successfully",
    "status_id": 2
}
```

#### GET /get_statuses/&lt;project_id&gt;
Get all statuses for a specific project.

**Response:**
```json
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
```

### Users

#### POST /create_user
Create a new user.

**Request:**
```json
{
    "user_name": "John Doe",
    "email": "john@example.com",
    "created_by": 1
}
```

**Response:**
```json
{
    "success": true,
    "message": "User created successfully",
    "user_id": 1
}
```

#### GET /get_users
Get all active users.

**Response:**
```json
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
```

## Error Handling

All API responses follow a consistent format:

**Success Response:**
```json
{
    "success": true,
    "message": "Operation completed successfully",
    "data": {...}
}
```

**Error Response:**
```json
{
    "success": false,
    "message": "Error description"
}
```

### HTTP Status Codes

- `200` - OK (successful GET/PUT request)
- `201` - Created (successful POST request)
- `400` - Bad Request (validation error)
- `404` - Not Found (resource not found)
- `405` - Method Not Allowed
- `500` - Internal Server Error
- `503` - Service Unavailable (database connection failed)

## Security Features

✅ **Parameterized SQL Queries** - Prevents SQL injection attacks  
✅ **Transaction Management** - Automatic rollback on errors  
✅ **Input Validation** - All inputs validated before database operations  
✅ **CORS Support** - Configured for cross-origin requests  
✅ **Error Handling** - Comprehensive error handling with appropriate status codes  

## Development

### Running in Debug Mode

The application runs in debug mode by default. To disable:

Edit `app.py` and change:
```python
app.run(debug=False)
```

### Testing the API

Use tools like:
- **Postman** - GUI REST client
- **curl** - Command-line tool
- **VS Code REST Client** - VS Code extension

Example with curl:
```bash
curl -X POST http://localhost:5000/create_project \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project", "description": "Test", "created_by": 1}'
```

## Troubleshooting

### Database Connection Error
- Verify MySQL is running
- Check DB credentials in `.env` file
- Ensure `kanban_db` database exists

### Import Error: mysql.connector
```bash
pip install mysql-connector-python
```

### Port Already in Use
Change the port in `app.py`:
```python
app.run(port=5001)
```

### CORS Issues
The API has CORS enabled by default. If you still encounter CORS errors, verify the frontend is making requests to the correct API URL.

## Architecture

The application is built as a single Python file (`app.py`) with:

- **Database Connection Pool** - Efficient database connection management
- **Parameterized Queries** - SQL injection protection
- **Transaction Management** - Automatic commit/rollback
- **Error Handling** - Comprehensive error handling
- **Validation** - Input validation before database operations
- **REST Conventions** - Standard HTTP methods and status codes

## Future Enhancements

- Add authentication and authorization
- Add rate limiting
- Add request logging
- Add pagination for list endpoints
- Add filtering and sorting options
- Add API versioning
- Add webhook support for real-time updates
- Add batch operations support

## License

MIT License

## Support

For issues or questions, please create an issue in the repository.
