import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError, forkJoin, map, of, switchMap, throwError } from 'rxjs';

import { Project } from '../models/project.model';
import { Task } from '../models/task.model';
import { User } from '../models/user.model';

interface ProjectApiResponse {
  success: boolean;
  projects?: Array<{
    id: string;
    name: string;
    description?: string;
    created_by?: number;
    created_at?: string;
    updated_at?: string;
  }>;
  project_id?: string;
  message?: string;
}

interface TicketApiResponse {
  success: boolean;
  tickets?: Array<{
    id: number;
    project_id: string;
    title: string;
    description?: string;
    status_id?: number;
    assigned_user_id?: number;
    created_by?: number;
    due_date?: string;
    created_at?: string;
    updated_at?: string;
  }>;
  ticket_id?: number;
  message?: string;
}

interface StatusApiResponse {
  success: boolean;
  statuses?: Array<{
    id: number;
    project_id: string;
    name: string;
    description?: string;
    sort_order?: number;
    is_active?: boolean;
    created_at?: string;
  }>;
  status_id?: number;
  message?: string;
}

interface UserApiResponse {
  success: boolean;
  users?: Array<{
    user_id: number;
    user_name: string;
    email?: string;
    is_active?: boolean;
    created_at?: string;
  }>;
  user_id?: number;
  message?: string;
}

@Injectable({
  providedIn: 'root'
})
export class KanbanService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = 'http://localhost:5000';
  private readonly projectStorageKey = 'kanban-projects';
  private readonly activeProjectStorageKey = 'kanban-active-project';
  private readonly taskStorageKey = 'kanban-tasks';

  private projects: Project[] = [];
  private activeProject: Project | null = null;
  private tasks: Task[] = [];

  createProject(projectName: string, statuses: string[], users: User[] = []): Observable<Project> {
    const sanitizedStatuses = this.normalizeStatuses(statuses);
    
    // Extract user IDs from the selected users
    const userIds = users
      .map((user) => {
        const numId = parseInt(user.id, 10);
        return isNaN(numId) ? null : numId;
      })
      .filter((id): id is number => id !== null);

    // Create comprehensive payload for single API call
    const projectPayload = {
      project_name: projectName.trim(),
      description: '',
      status: sanitizedStatuses,
      users: userIds
    };

    return this.http.post<ProjectApiResponse>(`${this.apiBaseUrl}/create_project`, projectPayload).pipe(
      map((projectResponse) => {
        const projectId = projectResponse.project_id ?? this.generateId();
        
        const project: Project = {
          id: projectId,
          projectName: projectName.trim(),
          statuses: sanitizedStatuses,
          users: users
        };

        this.projects = [...this.projects, project];
        this.activeProject = project;
        this.persistProjects();
        return project;
      }),
      catchError((error) => {
        console.error('Error creating project.', error);
        return throwError(() => error);
      })
    );
  }

  getUsers(): Observable<User[]> {
    return this.http.get<UserApiResponse>(`${this.apiBaseUrl}/get_users`).pipe(
      map((response) => {
        if (!response.success || !response.users) {
          return [];
        }

        return response.users.map((user) => ({
          id: String(user.user_id),
          name: user.user_name,
          email: user.email ?? undefined
        }));
      }),
      catchError((error) => {
        console.error('Failed to load users from API.', error);
        return of([]);
      })
    );
  }

  getProjects(): Observable<Project[]> {
    return this.http.get<ProjectApiResponse>(`${this.apiBaseUrl}/get_projects`).pipe(
      switchMap((response) => {
        if (!response.success || !response.projects) {
          return of([]);
        }

        const projectRequests = response.projects.map((project) =>
          forkJoin({
            statuses: this.fetchProjectStatuses(project.id),
            users: this.fetchUsers()
          }).pipe(
            map(({ statuses, users }) => ({
              id: project.id,
              projectName: project.name,
              statuses,
              users
            }) as Project)
          )
        );

        return projectRequests.length ? forkJoin(projectRequests) : of([]);
      }),
      map((mappedProjects) => {
        this.projects = mappedProjects;
        if (!this.activeProject && mappedProjects.length > 0) {
          this.activeProject = mappedProjects[0];
        }
        this.persistProjects();
        return [...this.projects];
      }),
      catchError((error) => {
        console.error('Failed to load projects from API.', error);
        return of([]);
      })
    );
  }

  selectProject(projectId: string): Observable<Project | null> {
    const project = this.projects.find((item) => item.id === projectId) ?? null;
    this.activeProject = project;

    if (project) {
      localStorage.setItem(this.activeProjectStorageKey, JSON.stringify(project.id));
      return this.getTasks(project.id).pipe(
        map((tasks) => {
          this.tasks = tasks;
          return project;
        })
      );
    }

    localStorage.removeItem(this.activeProjectStorageKey);
    this.tasks = [];
    return of(null);
  }

  getCurrentProject(): Project | null {
    return this.activeProject;
  }

  getTasks(projectId: string | null | undefined = this.activeProject?.id): Observable<Task[]> {
    if (!projectId) {
      return of([]);
    }

    return this.http.get<TicketApiResponse>(`${this.apiBaseUrl}/get_tickets/${projectId}`).pipe(
      switchMap((response) => {
        if (!response.success || !response.tickets) {
          return of([]);
        }

        return this.fetchUsers().pipe(
          map((users) => 
            response.tickets!.map((ticket) => {
              const assignee = users.find((user) => user.id === String(ticket.assigned_user_id));
              const statusName = this.resolveStatusName(projectId, ticket.status_id);

              return {
                id: String(ticket.id),
                projectId: ticket.project_id,
                title: ticket.title,
                description: ticket.description ?? '',
                status: statusName || 'New',
                dueDate: ticket.due_date ? new Date(ticket.due_date) : undefined,
                assignee
              } satisfies Task;
            })
          )
        );
      }),
      map((mappedTasks) => {
        this.tasks = mappedTasks;
        this.persistTasks();
        return [...mappedTasks];
      }),
      catchError((error) => {
        console.error('Failed to load tickets from API.', error);
        return of([]);
      })
    );
  }

  upsertTask(task: Task): Observable<Task> {
    const project = this.activeProject ?? this.projects.find((item) => item.id === task.projectId) ?? null;
    const statusId = this.resolveStatusId(project, task.status);
    const assignedUserId = task.assignee ? Number(task.assignee.id) : undefined;
    const isExistingBackendTask = task.id && /^\d+$/.test(task.id);

    if (!isExistingBackendTask) {
      return this.http.post<TicketApiResponse>(`${this.apiBaseUrl}/create_ticket`, {
        project_id: task.projectId,
        title: task.title,
        description: task.description ?? '',
        status_id: statusId ?? 1,
        assigned_user_id: assignedUserId ?? null,
        created_by: 1,
        due_date: task.dueDate ? task.dueDate.toISOString() : null
      }).pipe(
        map((response) => {
          const createdTask = {
            ...task,
            id: response.ticket_id ? String(response.ticket_id) : task.id
          };
          this.tasks = [...this.tasks.filter((item) => item.id !== task.id), createdTask];
          this.persistTasks();
          return createdTask;
        }),
        catchError((error) => {
          console.error('Error creating ticket.', error);
          return throwError(() => error);
        })
      );
    }

    return this.http.put<TicketApiResponse>(`${this.apiBaseUrl}/edit_ticket`, {
      ticket_id: Number(task.id),
      title: task.title,
      description: task.description ?? '',
      status_id: statusId ?? null,
      assigned_user_id: assignedUserId ?? null,
      due_date: task.dueDate ? task.dueDate.toISOString() : null,
      updated_by: 1
    }).pipe(
      map(() => {
        this.tasks = this.tasks.map((item) => (item.id === task.id ? task : item));
        this.persistTasks();
        return task;
      }),
      catchError((error) => {
        console.error('Error updating ticket.', error);
        return throwError(() => error);
      })
    );
  }

  updateTaskStatus(taskId: string, status: string): Observable<Task | null> {
    const task = this.tasks.find((item) => item.id === taskId);
    if (!task) {
      return of(null);
    }

    const project = this.activeProject ?? this.projects.find((item) => item.id === task.projectId) ?? null;
    const statusId = this.resolveStatusId(project, status);

    if (!/^\d+$/.test(taskId)) {
      task.status = status;
      this.tasks = this.tasks.map((item) => (item.id === taskId ? task : item));
      return of(task);
    }

    return this.http.put<{ success: boolean; message?: string }>(`${this.apiBaseUrl}/update_status`, {
      ticket_id: Number(taskId),
      status_id: statusId ?? 1
    }).pipe(
      map(() => {
        task.status = status;
        this.tasks = this.tasks.map((item) => (item.id === taskId ? task : item));
        return task;
      }),
      catchError((error) => {
        console.error('Error updating task status.', error);
        return throwError(() => error);
      })
    );
  }

  private fetchProjectStatuses(projectId: string): Observable<string[]> {
    return this.http.get<StatusApiResponse>(`${this.apiBaseUrl}/get_statuses/${projectId}`).pipe(
      map((response) => {
        if (!response.success || !response.statuses) {
          return ['New', 'On-going', 'Completed'];
        }

        return response.statuses
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
          .map((status) => status.name);
      }),
      catchError(() => of(['New', 'On-going', 'Completed']))
    );
  }

  private fetchUsers(): Observable<User[]> {
    return this.http.get<UserApiResponse>(`${this.apiBaseUrl}/get_users`).pipe(
      map((response) => {
        if (!response.success || !response.users) {
          return [];
        }

        return response.users.map((user) => ({
          id: String(user.user_id),
          name: user.user_name,
          email: user.email ?? undefined
        }));
      }),
      catchError(() => of([]))
    );
  }

  private resolveStatusName(projectId: string, statusId?: number): string {
    const project = this.projects.find((item) => item.id === projectId);
    if (!project || statusId == null) {
      return 'New';
    }

    const statusIndex = this.getStatusMap(project)?.get(statusId);
    return statusIndex ?? 'New';
  }

  private resolveStatusId(project: Project | null, statusName: string): number | null {
    if (!project) {
      return null;
    }

    const statusMap = this.getStatusMap(project);
    if (!statusMap) {
      return null;
    }

    const match = [...statusMap.entries()].find(([, value]) => value.toLowerCase() === statusName.trim().toLowerCase());
    return match ? match[0] : null;
  }

  private getStatusMap(project: Project): Map<number, string> | null {
    const statusNames = project.statuses ?? [];
    if (statusNames.length === 0) {
      return null;
    }

    return new Map(
      statusNames.map((name, index) => [index + 1, name])
    );
  }

  private loadProjects(): Project[] {
    try {
      const storedProjects = localStorage.getItem(this.projectStorageKey);
      if (!storedProjects) {
        return [];
      }

      const parsedProjects = JSON.parse(storedProjects) as Project[];
      return Array.isArray(parsedProjects) ? parsedProjects : [];
    } catch {
      return [];
    }
  }

  private loadActiveProject(): Project | null {
    try {
      const storedProjectId = localStorage.getItem(this.activeProjectStorageKey);
      if (!storedProjectId) {
        return this.projects[0] ?? null;
      }

      const project = this.projects.find((item) => item.id === storedProjectId);
      return project ?? this.projects[0] ?? null;
    } catch {
      return this.projects[0] ?? null;
    }
  }

  private persistProjects(): void {
    localStorage.setItem(this.projectStorageKey, JSON.stringify(this.projects));
    if (this.activeProject) {
      localStorage.setItem(this.activeProjectStorageKey, JSON.stringify(this.activeProject.id));
    }
  }

  private loadTasks(): Task[] {
    try {
      const storedTasks = localStorage.getItem(this.taskStorageKey);
      return storedTasks ? (JSON.parse(storedTasks) as Task[]) : [];
    } catch {
      return [];
    }
  }

  private persistTasks(): void {
    localStorage.setItem(this.taskStorageKey, JSON.stringify(this.tasks));
  }

  private normalizeStatuses(statuses: string[]): string[] {
    const uniqueStatuses = new Set<string>();

    for (const status of statuses) {
      const normalizedValue = status.trim();
      if (!normalizedValue) {
        continue;
      }

      if (!uniqueStatuses.has(normalizedValue.toLowerCase())) {
        uniqueStatuses.add(normalizedValue.toLowerCase());
      }
    }

    return Array.from(uniqueStatuses, (value) => {
      const originalStatus = statuses.find(
        (status) => status.trim().toLowerCase() === value
      );

      return originalStatus?.trim() ?? value;
    });
  }

  private generateId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `project-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}
