import { User } from './user.model';

export interface Task {
  id: string;
  projectId: string;
  title: string;
  description?: string;
  status: string;
  dueDate?: Date;
  assignee?: User;
}
