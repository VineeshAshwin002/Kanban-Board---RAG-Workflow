import { CommonModule, DatePipe } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators
} from '@angular/forms';

import { Task } from '../models/task.model';
import { User } from '../models/user.model';

export interface TaskDialogData {
  taskId?: string;
  title: string;
  description?: string;
  status: string;
  dueDate?: Date;
  assignee?: User;
  statusOptions: string[];
  userOptions: User[];
}

@Component({
  selector: 'app-dialog',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './dialog.component.html',
  styleUrl: './dialog.component.scss',
  providers: [DatePipe]
})
export class DialogComponent {
  private editingTaskId: string | null = null;

  @Input() set dialogData(value: TaskDialogData | null) {
    if (!value) {
      return;
    }

    this.editingTaskId = value.taskId ?? null;
    this.taskForm.reset({
      title: value.title ?? '',
      description: value.description ?? '',
      status: value.status,
      assignee: value.assignee?.id ?? '',
      dueDate: value.dueDate ? this.formatDateForInput(value.dueDate) : ''
    });
    this.statusOptions = value.statusOptions;
    this.userOptions = value.userOptions;
  }

  @Output() saveTask = new EventEmitter<Task>();
  @Output() closeDialog = new EventEmitter<void>();

  protected taskForm = new FormGroup({
    title: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required]
    }),
    description: new FormControl('', {
      nonNullable: true
    }),
    status: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required]
    }),
    assignee: new FormControl('', {
      nonNullable: true
    }),
    dueDate: new FormControl('', {
      nonNullable: true
    })
  });

  protected statusOptions: string[] = [];
  protected userOptions: User[] = [];

  protected get titleControl(): FormControl<string> {
    return this.taskForm.controls.title as FormControl<string>;
  }

  protected get statusControl(): FormControl<string> {
    return this.taskForm.controls.status as FormControl<string>;
  }

  protected get isEditMode(): boolean {
    return !!this.editingTaskId;
  }

  protected submitTask(): void {
    this.titleControl.markAsTouched();
    this.statusControl.markAsTouched();

    if (this.taskForm.invalid) {
      return;
    }

    const formValue = this.taskForm.getRawValue();
    const parsedDate = formValue.dueDate ? new Date(formValue.dueDate) : undefined;

    // Find the selected user if assignee is provided
    const assignee = formValue.assignee
      ? this.userOptions.find((user) => user.id === formValue.assignee)
      : undefined;

    const task: Task = {
      id: this.editingTaskId ?? this.generateId(),
      projectId: '',
      title: formValue.title.trim(),
      description: formValue.description?.trim() || undefined,
      status: formValue.status,
      assignee: assignee,
      dueDate: parsedDate && !Number.isNaN(parsedDate.getTime()) ? parsedDate : undefined
    };

    this.saveTask.emit(task);
  }

  protected close(): void {
    this.closeDialog.emit();
  }

  private formatDateForInput(date: Date): string {
    const normalizedDate = new Date(date);
    const offset = normalizedDate.getTimezoneOffset();
    const adjustedDate = new Date(normalizedDate.getTime() - offset * 60 * 1000);
    return adjustedDate.toISOString().slice(0, 10);
  }

  private generateId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}
