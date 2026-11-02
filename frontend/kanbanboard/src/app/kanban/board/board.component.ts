import { CdkDrag, CdkDragDrop, CdkDropList, CdkDropListGroup } from '@angular/cdk/drag-drop';
import { CommonModule, DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Project } from '../models/project.model';
import { Task } from '../models/task.model';

@Component({
  selector: 'app-board',
  standalone: true,
  imports: [CommonModule, CdkDropListGroup, CdkDropList, CdkDrag, RouterLink],
  templateUrl: './board.component.html',
  styleUrl: './board.component.scss',
  providers: [DatePipe]
})
export class BoardComponent {
  @Input() project: Project | null = null;
  @Input() tasks: Task[] = [];
  @Output() addTask = new EventEmitter<void>();
  @Output() editTask = new EventEmitter<Task>();
  @Output() taskMoved = new EventEmitter<{ taskId: string; newStatus: string }>();

  private readonly columnTaskCache = new Map<string, { source: Task[]; tasks: Task[] }>();

  protected get columns(): string[] {
    return this.project?.statuses ?? [];
  }

  protected getColumnTasks(status: string): Task[] {
    const cached = this.columnTaskCache.get(status);
    if (cached?.source === this.tasks) {
      return cached.tasks;
    }

    const tasks = this.tasks.filter((task) => task.status === status);
    this.columnTaskCache.set(status, { source: this.tasks, tasks });
    return tasks;
  }

  protected getStatusId(status: string): string {
    return status.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
  }

  protected resolveStatusFromDropId(dropId: string): string {
    const normalizedId = dropId.replace('cdk-drop-list-', '');
    const match = this.project?.statuses.find(
      (status) => this.getStatusId(status) === normalizedId
    );

    return match ?? normalizedId;
  }

  protected onTaskDrop(event: CdkDragDrop<Task[]>) {
    if (!this.project || event.previousContainer === event.container) {
      return;
    }

    const movedTask = event.item.data as Task | undefined;
    if (!movedTask) {
      return;
    }

    const previousStatus = this.resolveStatusFromDropId(event.previousContainer.id);
    const newStatus = this.resolveStatusFromDropId(event.container.id);

    // The drop-list data is a filtered view, so update the source task through the parent.
    this.taskMoved.emit({
      taskId: movedTask.id,
      newStatus: newStatus || previousStatus
    });
  }

  protected openCreateTaskDialog(): void {
    this.addTask.emit();
  }

  protected openEditTaskDialog(task: Task): void {
    this.editTask.emit(task);
  }
}
