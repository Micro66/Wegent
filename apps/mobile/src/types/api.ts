// ---- User ----
export interface User {
  id: number
  user_name: string
  email: string
  is_active: boolean
  created_at: string
}

// ---- Team / Agent ----
export interface Team {
  id: number
  name: string
  namespace: string
  description?: string
  avatar?: string
  created_at: string
  updated_at: string
}

export interface TeamListResponse {
  total: number
  items: Team[]
}

// ---- Task / Conversation ----
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Task {
  id: number
  title: string
  team_id: number
  team_name?: string
  status: TaskStatus
  created_at: string
  updated_at: string
}

export interface TaskListResponse {
  total: number
  items: Task[]
}

export interface TaskDetail extends Task {
  team_id: number
  team_name: string
  subtasks?: SubTask[]
}

// ---- SubTask / Message ----
export interface SubTask {
  subtask_id: number
  task_id: number
  message_id: number
  role: 'USER' | 'ASSISTANT'
  content: string
  status: string
  bot_name?: string
  sender_user_id?: number
  sender_user_name?: string
  created_at: string
}

export interface SubTaskListResponse {
  total: number
  items: SubTask[]
}

// ---- Model ----
export interface UnifiedModel {
  name: string
  model_type?: string
  provider?: string
  description?: string
  shell_type?: string
}

export interface UnifiedModelListResponse {
  items: UnifiedModel[]
}

// ---- Pagination ----
export interface PaginationParams {
  page?: number
  limit?: number
}
