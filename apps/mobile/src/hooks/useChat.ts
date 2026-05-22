import { useState, useRef, useCallback, useEffect } from 'react'
import { connectSocket, getSocket } from '@/lib/socket-client'
import { apiFetch } from '@/lib/api-client'
import type { SubTask, SubTaskListResponse } from '@/types/api'
import { ClientEvents, ServerEvents } from '@/types/socket'
import type {
  ChatSendPayload,
  ChatStartPayload,
  ChatChunkPayload,
  ChatDonePayload,
  ChatErrorPayload,
  ChatCancelledPayload,
} from '@/types/socket'

export interface UIMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  status: 'pending' | 'streaming' | 'completed' | 'error'
  subtaskId?: number
  messageId?: number
  botName?: string
  error?: string
  timestamp: number
}

export function useChat() {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null)
  const streamingSubtaskRef = useRef<number | null>(null)

  // Connect socket on mount
  useEffect(() => {
    try {
      connectSocket()
    } catch {
      // Token not available yet — socket will connect after login
    }
  }, [])

  // Listen for streaming events
  useEffect(() => {
    const socket = getSocket()
    if (!socket) return

    const handleStart = (p: ChatStartPayload) => {
      setIsStreaming(true)
      streamingSubtaskRef.current = p.subtask_id
      setMessages(prev => {
        const existing = prev.find(m => m.subtaskId === p.subtask_id)
        if (existing) {
          return prev.map(m =>
            m.subtaskId === p.subtask_id
              ? { ...m, status: 'streaming' as const }
              : m,
          )
        }
        return [
          ...prev,
          {
            id: `ai-${p.subtask_id}`,
            role: 'ai',
            content: '',
            status: 'streaming',
            subtaskId: p.subtask_id,
            messageId: p.message_id,
            botName: p.bot_name,
            timestamp: Date.now(),
          },
        ]
      })
    }

    const handleChunk = (p: ChatChunkPayload) => {
      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? { ...m, content: m.content + p.content }
            : m,
        ),
      )
    }

    const handleDone = (p: ChatDonePayload) => {
      setIsStreaming(false)
      streamingSubtaskRef.current = null
      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? {
                ...m,
                status: 'completed' as const,
                content:
                  (typeof p.result?.value === 'string' ? p.result.value : '') ||
                  m.content,
              }
            : m,
        ),
      )
    }

    const handleError = (p: ChatErrorPayload) => {
      setIsStreaming(false)
      streamingSubtaskRef.current = null
      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? { ...m, status: 'error' as const, error: p.error }
            : m,
        ),
      )
    }

    const handleCancelled = (p: ChatCancelledPayload) => {
      setIsStreaming(false)
      streamingSubtaskRef.current = null
      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? { ...m, status: 'completed' as const }
            : m,
        ),
      )
    }

    socket.on(ServerEvents.CHAT_START, handleStart)
    socket.on(ServerEvents.CHAT_CHUNK, handleChunk)
    socket.on(ServerEvents.CHAT_DONE, handleDone)
    socket.on(ServerEvents.CHAT_ERROR, handleError)
    socket.on(ServerEvents.CHAT_CANCELLED, handleCancelled)

    return () => {
      socket.off(ServerEvents.CHAT_START, handleStart)
      socket.off(ServerEvents.CHAT_CHUNK, handleChunk)
      socket.off(ServerEvents.CHAT_DONE, handleDone)
      socket.off(ServerEvents.CHAT_ERROR, handleError)
      socket.off(ServerEvents.CHAT_CANCELLED, handleCancelled)
    }
  }, [])

  // Load message history for a task
  const loadMessages = useCallback(async (taskId: number) => {
    setActiveTaskId(taskId)
    const socket = getSocket()
    if (socket) {
      socket.emit(ClientEvents.TASK_JOIN, { task_id: taskId })
    }

    try {
      const res = await apiFetch<SubTaskListResponse>(
        `/subtasks?task_id=${taskId}&limit=100&from_latest=true`,
      )
      const history: UIMessage[] = res.items.map((st: SubTask) => ({
        id: `msg-${st.subtask_id}`,
        role: st.role === 'USER' ? 'user' : 'ai',
        content: st.content,
        status: 'completed' as const,
        subtaskId: st.subtask_id,
        messageId: st.message_id,
        botName: st.bot_name,
        timestamp: new Date(st.created_at).getTime(),
      }))
      setMessages(history)
    } catch (e) {
      console.error('Failed to load messages', e)
    }
  }, [])

  // Send message via WebSocket
  const sendMessage = useCallback(
    (teamId: number, message: string, taskId?: number) => {
      const socket = getSocket()
      if (!socket) {
        console.error('Socket not connected')
        return
      }

      const payload: ChatSendPayload = {
        team_id: teamId,
        message,
        task_id: taskId ?? activeTaskId ?? undefined,
      }
      socket.emit(ClientEvents.CHAT_SEND, payload)

      // Add user message optimistically
      setMessages(prev => [
        ...prev,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content: message,
          status: 'completed',
          timestamp: Date.now(),
        },
      ])
    },
    [activeTaskId],
  )

  // Cancel/stop streaming
  const stopStream = useCallback(() => {
    const socket = getSocket()
    const subtaskId = streamingSubtaskRef.current
    if (socket && subtaskId) {
      socket.emit(ClientEvents.CHAT_CANCEL, { subtask_id: subtaskId })
    }
  }, [])

  // Clear messages (for new chat)
  const clearMessages = useCallback(() => {
    const socket = getSocket()
    if (socket && activeTaskId) {
      socket.emit(ClientEvents.TASK_LEAVE, { task_id: activeTaskId })
    }
    setMessages([])
    setActiveTaskId(null)
    setIsStreaming(false)
  }, [activeTaskId])

  return {
    messages,
    isStreaming,
    activeTaskId,
    sendMessage,
    stopStream,
    loadMessages,
    clearMessages,
  }
}
