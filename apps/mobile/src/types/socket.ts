// Client -> Server Events
export const ClientEvents = {
  CHAT_SEND: 'chat:send',
  CHAT_CANCEL: 'chat:cancel',
  CHAT_RETRY: 'chat:retry',
  TASK_JOIN: 'task:join',
  TASK_LEAVE: 'task:leave',
} as const

// Server -> Client Events
export const ServerEvents = {
  AUTH_ERROR: 'auth:error',
  TASK_CREATED: 'task:created',
  CHAT_START: 'chat:start',
  CHAT_CHUNK: 'chat:chunk',
  CHAT_DONE: 'chat:done',
  CHAT_ERROR: 'chat:error',
  CHAT_CANCELLED: 'chat:cancelled',
  CHAT_BLOCK_CREATED: 'chat:block_created',
  CHAT_BLOCK_UPDATED: 'chat:block_updated',
  CHAT_MESSAGE: 'chat:message',
} as const

export interface TaskCreatedPayload {
  task_id: number
  title: string
  team_id: number
  team_name: string
  created_at: string
  is_group_chat?: boolean
}

export interface ChatSendPayload {
  task_id?: number
  team_id: number
  message: string
  title?: string
}

export interface ChatCancelPayload {
  subtask_id: number
}

export interface TaskJoinPayload {
  task_id: number
}

export interface TaskLeavePayload {
  task_id: number
}

export interface ChatStartPayload {
  task_id: number
  subtask_id: number
  bot_name?: string
  message_id?: number
}

export interface ChatChunkPayload {
  subtask_id: number
  content: string
  offset: number
  task_id?: number
  block_id?: string
  block_offset?: number
  result?: {
    value?: string
    reasoning_chunk?: string
    reasoning_content?: string
    thinking?: unknown[]
    blocks?: import('@/types/api').MessageBlock[]
  }
}

export interface ChatDonePayload {
  task_id?: number
  subtask_id: number
  offset: number
  result: Record<string, unknown> & {
    value?: string
    reasoning_content?: string
    thinking?: unknown[]
    blocks?: import('@/types/api').MessageBlock[]
  }
  message_id?: number
}

export interface ChatErrorPayload {
  subtask_id: number
  error: string
  type?: string
  message_id?: number
  task_id?: number
}

export interface ChatCancelledPayload {
  task_id: number
  subtask_id: number
}

export interface ChatBlockCreatedPayload {
  task_id: number
  subtask_id: number
  block: import('@/types/api').MessageBlock
}

export interface ChatBlockUpdatedPayload {
  task_id: number
  subtask_id: number
  block_id: string
  content?: string
  tool_output?: unknown
  tool_input?: Record<string, unknown>
  argument_status?: 'streaming' | 'done'
  status?: import('@/types/api').MessageBlock['status'] | 'running'
}

export interface ChatMessagePayload {
  subtask_id: number
  task_id: number
  message_id: number
  role: string
  content: string
  sender: {
    user_id: number
    user_name: string
    avatar?: string
  }
  created_at: string
}

export interface TaskJoinAck {
  streaming?: {
    subtask_id: number
    offset: number
    cached_content: string
  }
  subtasks?: Array<Record<string, unknown>>
  error?: string
}
