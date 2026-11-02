import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output, OnInit, inject, signal } from '@angular/core';
import {
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators
} from '@angular/forms';

import { Project } from '../models/project.model';
import { User } from '../models/user.model';
import { KanbanService } from '../services/kanban.service';

@Component({
  selector: 'app-create-project',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './create-project.component.html',
  styleUrl: './create-project.component.scss'
})
export class CreateProjectComponent implements OnInit {
  @Output() projectCreated = new EventEmitter<Project>();
  @Output() closeRequested = new EventEmitter<void>();

  private readonly kanbanService = inject(KanbanService);

  protected readonly defaultStatuses = ['New', 'On-going', 'Completed'];
  protected statuses = [...this.defaultStatuses];
  protected users: User[] = [];
  protected allUsers: User[] = [];
  protected isSubmitting = signal(false);

  ngOnInit(): void {
    this.loadUsers();
  }

  protected readonly projectForm = new FormGroup({
    projectName: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required]
    }),
    statusInput: new FormControl('', {
      nonNullable: true
    }),
    userInput: new FormControl<string[]>([], {
      nonNullable: true
    })
  });

  protected get projectNameControl(): FormControl<string> {
    return this.projectForm.controls.projectName as FormControl<string>;
  }

  protected get statusInputControl(): FormControl<string> {
    return this.projectForm.controls.statusInput as FormControl<string>;
  }

  protected get userInputControl(): FormControl<string[]> {
    return this.projectForm.controls.userInput as FormControl<string[]>;
  }

  protected closeModal(): void {
    this.closeRequested.emit();
    this.resetForm();
  }

  protected addStatus(): void {
    const status = this.statusInputControl.value.trim();

    if (!status) {
      this.statusInputControl.setErrors({ emptyStatus: true });
      this.statusInputControl.markAsTouched();
      return;
    }

    const normalizedStatus = status.toLowerCase();
    const hasDuplicate = this.statuses.some(
      (existingStatus) => existingStatus.trim().toLowerCase() === normalizedStatus
    );

    if (hasDuplicate) {
      this.statusInputControl.setErrors({ duplicate: true });
      this.statusInputControl.markAsTouched();
      return;
    }

    this.statuses.push(status);
    this.statusInputControl.reset();
    this.statusInputControl.setErrors(null);
  }

  protected removeStatus(index: number): void {
    // Prevent removing the last status
    if (this.statuses.length <= 1) {
      return;
    }

    this.statuses.splice(index, 1);
  }

  protected addUser(): void {
    const selectedUserIds = Array.isArray(this.userInputControl.value)
      ? this.userInputControl.value
      : this.userInputControl.value ? [this.userInputControl.value] : [];

    if (!selectedUserIds.length) {
      this.userInputControl.setErrors({ emptyUser: true });
      this.userInputControl.markAsTouched();
      return;
    }

    const newUsers = selectedUserIds
      .map((userId) => this.allUsers.find((user) => user.id === userId))
      .filter((user): user is User => !!user)
      .filter((user) => !this.users.some((existingUser) => existingUser.id === user.id));

    if (!newUsers.length) {
      this.userInputControl.setErrors({ duplicateUser: true });
      this.userInputControl.markAsTouched();
      return;
    }

    this.users.push(...newUsers);
    this.userInputControl.reset([]);
    this.userInputControl.setErrors(null);
  }

  protected removeUser(index: number): void {
    this.users.splice(index, 1);
  }

  protected submitProject(): void {
    // Mark all fields as touched to show validation errors
    this.projectNameControl.markAsTouched();
    this.statusInputControl.markAsTouched();

    // Validate form
    if (this.projectNameControl.invalid) {
      return;
    }

    // Validate project name is not empty after trimming
    const trimmedProjectName = this.projectNameControl.value.trim();
    if (!trimmedProjectName) {
      this.projectNameControl.setErrors({ required: true });
      return;
    }

    // Validate statuses exist
    if (this.statuses.length === 0) {
      this.statusInputControl.setErrors({ emptyStatus: true });
      return;
    }

    // Prepare and validate status data
    const trimmedStatuses = this.statuses
      .map((status) => status.trim())
      .filter((status) => status.length > 0);

    if (trimmedStatuses.length === 0) {
      this.statusInputControl.setErrors({ emptyStatus: true });
      return;
    }

    // Check for duplicate statuses (case-insensitive)
    const uniqueStatuses = new Set<string>();
    for (const status of trimmedStatuses) {
      if (uniqueStatuses.has(status.toLowerCase())) {
        this.statusInputControl.setErrors({ duplicate: true });
        return;
      }
      uniqueStatuses.add(status.toLowerCase());
    }

    // Prevent duplicate submissions
    if (this.isSubmitting()) {
      return;
    }

    // Set loading state
    this.isSubmitting.set(true);

    // Create project object
    const project: Project = {
      id: this.generateId(),
      projectName: trimmedProjectName,
      statuses: trimmedStatuses,
      users: this.users
    };

    // Emit project creation event
    this.projectCreated.emit(project);

    // Reset form state
    this.resetForm();

    // Reset loading state (in a real app, this would be in a callback after API response)
    setTimeout(() => {
      this.isSubmitting.set(false);
    }, 500);
  }

  private loadUsers(): void {
    this.kanbanService.getUsers().subscribe({
      next: (loadedUsers) => {
        this.allUsers = Array.isArray(loadedUsers) ? loadedUsers : [];
        this.userInputControl.reset([]);
      },
      error: (error) => console.error('Failed to load users for project creation.', error),
      complete: () => undefined
    });
  }

  protected trackUser(index: number, user: User): string {
    return user?.id ?? `${index}`;
  }

  private resetForm(): void {
    this.projectForm.reset();
    this.statuses = [...this.defaultStatuses];
    this.users = [];
    this.userInputControl.setErrors(null);
  }

  private generateId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }

    return `project-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}
