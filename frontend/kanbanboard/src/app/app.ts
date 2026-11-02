import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterOutlet } from '@angular/router';

import { BoardComponent } from './kanban/board/board.component';
import { CreateProjectComponent } from './kanban/create-project/create-project.component';
import { DialogComponent, type TaskDialogData } from './kanban/dialog/dialog.component';
import { Project } from './kanban/models/project.model';
import { Task } from './kanban/models/task.model';
import { KanbanService } from './kanban/services/kanban.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [BoardComponent, CreateProjectComponent, DialogComponent, RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  private readonly kanbanService = inject(KanbanService);
  protected readonly router = inject(Router);

  protected readonly projects = signal<Project[]>([]);
  protected readonly project = signal<Project | null>(null);
  protected readonly tasks = signal<Task[]>([]);
  protected readonly isProjectCreated = computed(() => !!this.project());
  protected readonly isDialogOpen = signal(false);
  protected readonly isProjectFormOpen = signal(false);
  protected readonly defaultStatus = computed(() => this.project()?.statuses[0] ?? '');

  protected activeTaskForm: Task | null = null;
  protected dialogData: TaskDialogData | null = null;

  constructor() {
    this.loadInitialState();
  }

  protected loadInitialState(): void {
    this.kanbanService.getProjects().subscribe({
      next: (loadedProjects) => {
        this.projects.set(loadedProjects);

        const currentProject = this.kanbanService.getCurrentProject() ?? loadedProjects[0] ?? null;
        if (currentProject) {
          this.kanbanService.selectProject(currentProject.id).subscribe({
            next: (selectedProject) => {
              this.project.set(selectedProject ?? currentProject);
              this.kanbanService.getTasks(currentProject.id).subscribe({
                next: (tasks) => this.tasks.set(tasks),
                error: (error) => console.error('Failed to load tasks.', error),
                complete: () => undefined
              });
            },
            error: (error) => console.error('Failed to select project.', error),
            complete: () => undefined
          });
        }
      },
      error: (error) => console.error('Failed to initialize Kanban app state.', error),
      complete: () => undefined
    });
  }

  protected refreshProjectState(): void {
    const currentProject = this.kanbanService.getCurrentProject();
    this.kanbanService.getProjects().subscribe({
      next: (loadedProjects) => {
        this.projects.set(loadedProjects);
        const nextProject = currentProject ?? loadedProjects[0] ?? null;
        this.project.set(nextProject);

        this.kanbanService.getTasks(nextProject?.id ?? null).subscribe({
          next: (tasks) => this.tasks.set(tasks),
          error: (error) => console.error('Failed to refresh tasks.', error),
          complete: () => undefined
        });
      },
      error: (error) => console.error('Failed to refresh project state.', error),
      complete: () => undefined
    });
  }

  protected handleProjectCreate(project: Project): void {
    this.kanbanService.createProject(project.projectName, project.statuses, project.users).subscribe({
      next: (createdProject) => {
        this.kanbanService.selectProject(createdProject.id).subscribe({
          next: () => {
            this.refreshProjectState();
            this.isProjectFormOpen.set(false);
            this.isDialogOpen.set(false);
          },
          error: (error) => console.error('Failed to select created project.', error),
          complete: () => undefined
        });
      },
      error: (error) => console.error('Failed to create project.', error),
      complete: () => undefined
    });
  }

  protected openTaskDialog(task?: Task): void {
    if (!this.project()) {
      return;
    }

    this.activeTaskForm = task ?? null;
    const defaultStatus = this.project()!.statuses[0] ?? '';
    this.dialogData = {
      taskId: this.activeTaskForm?.id,
      title: this.activeTaskForm?.title ?? '',
      description: this.activeTaskForm?.description ?? '',
      status: this.activeTaskForm?.status ?? defaultStatus,
      assignee: this.activeTaskForm?.assignee,
      dueDate: this.activeTaskForm?.dueDate,
      statusOptions: this.project()!.statuses,
      userOptions: this.project()!.users
    };
    this.isDialogOpen.set(true);
  }

  protected openCreateProjectForm(): void {
    this.isProjectFormOpen.set(true);
  }

  protected closeCreateProjectForm(): void {
    this.isProjectFormOpen.set(false);
  }

  protected onTaskSave(task: Task): void {
    if (!this.project()) {
      return;
    }

    const projectId = this.project()!.id;
    const taskToSave: Task = {
      ...task,
      id: task.id || this.generateId(),
      projectId,
      status: task.status || this.defaultStatus() || this.project()!.statuses[0]
    };

    this.kanbanService.upsertTask(taskToSave).subscribe({
      next: () => {
        this.refreshProjectState();
        this.isDialogOpen.set(false);
        this.activeTaskForm = null;
        this.dialogData = null;
      },
      error: (error) => console.error('Failed to save task.', error),
      complete: () => undefined
    });
  }

  protected onTaskMove(event: { taskId: string; newStatus: string }): void {
    const currentProject = this.project();
    if (!currentProject) {
      return;
    }

    // Update the rendered state before starting the network request.
    this.tasks.update((tasks) => tasks.map((task) =>
      task.id === event.taskId ? { ...task, status: event.newStatus } : task
    ));

    this.kanbanService.updateTaskStatus(event.taskId, event.newStatus).subscribe({
      next: () => {
        // API call succeeded, local state is already updated
        // No need to refresh - the UI is already in sync
      },
      error: (error) => {
        console.error('Failed to move task.', error);
        // On error, refresh to restore correct state from server
        this.refreshProjectState();
      },
      complete: () => undefined
    });
  }

  protected selectProject(projectId: string): void {
    this.kanbanService.selectProject(projectId).subscribe({
      next: (selectedProject) => {
        if (selectedProject) {
          this.project.set(selectedProject);
          this.kanbanService.getTasks(selectedProject.id).subscribe({
            next: (tasks) => this.tasks.set(tasks),
            error: (error) => console.error('Failed to load selected project tasks.', error),
            complete: () => undefined
          });
        }
      },
      error: (error) => console.error('Failed to select project.', error),
      complete: () => undefined
    });
  }

  protected closeTaskDialog(): void {
    this.isDialogOpen.set(false);
    this.activeTaskForm = null;
    this.dialogData = null;
  }

  private generateId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}
