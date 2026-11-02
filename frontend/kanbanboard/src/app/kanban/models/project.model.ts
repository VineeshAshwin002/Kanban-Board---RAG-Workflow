import { User } from './user.model';

export interface Project {
  id: string;
  projectName: string;
  statuses: string[];
  users: User[];
}
