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
  agent_type?: string
  is_mix_team?: boolean
  bots?: TeamBot[]
  created_at: string
  updated_at: string
}

export interface AllowedModelRef {
  name: string
  type?: string
  namespace?: string
}

export interface BotSummary {
  agent_config?: Record<string, unknown> & {
    bind_model?: unknown
    allowed_models?: unknown
  }
  shell_type?: string
}

export interface TeamBot {
  bot_id: number
  bot_prompt?: string
  role?: string
  bot?: BotSummary
}

export interface TeamListResponse {
  total: number
  items: Team[]
}

// ---- Task / Conversation ----
export type TaskStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

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
  team?: Team
  model_id?: string | null
  subtasks?: SubTask[]
}

// ---- SubTask / Message ----
export interface SubTask {
  id: number
  task_id: number
  role: 'USER' | 'ASSISTANT'
  prompt?: string
  status: string
  message_id?: number
  bot_name?: string
  sender_user_id?: number
  sender_user_name?: string
  created_at: string
  result?: {
    value?: string
    thinking?: unknown[]
    reasoning_content?: string
    blocks?: MessageBlock[]
  }
}

export interface MessageBlock {
  id?: string
  type?: string
  status?: string
  content?: string
  timestamp?: number
  tool_use_id?: string
  tool_name?: string
  display_name?: string
  tool_input?: Record<string, unknown>
  tool_output?: unknown
  argument_status?: 'streaming' | 'done'
  image_urls?: string[]
  video_url?: string
}

export interface SubTaskListResponse {
  total: number
  items: SubTask[]
}

// ---- Model ----
export interface UnifiedModel {
  name: string
  type?: string
  displayName?: string
  provider?: string
  modelId?: string
  namespace?: string
  modelCategoryType?: string
  isAdvanced?: boolean
  config?: Record<string, unknown>
}

export interface UnifiedModelListResponse {
  data: UnifiedModel[]
}

// ---- Pagination ----
export interface PaginationParams {
  page?: number
  limit?: number
}
