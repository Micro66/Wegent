import { useState, useRef, useCallback, useEffect } from 'react'
import { connectSocket, getSocket } from '@/lib/socket-client'
import { apiFetch } from '@/lib/api-client'
import type { SubTask, SubTaskListResponse } from '@/types/api'
import type { MessageBlock } from '@/types/api'
import { ClientEvents, ServerEvents } from '@/types/socket'
import type {
  ChatSendPayload,
  ChatStartPayload,
  ChatChunkPayload,
  ChatDonePayload,
  ChatErrorPayload,
  ChatCancelledPayload,
  TaskCreatedPayload,
  ChatBlockCreatedPayload,
  ChatBlockUpdatedPayload,
} from '@/types/socket'

export interface UIMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  status: 'pending' | 'streaming' | 'completed' | 'error'
  subtaskId?: number
  messageId?: number
  botName?: string
  result?: {
    value?: string
    thinking?: unknown[]
    reasoning_content?: string
    blocks?: MessageBlock[]
  }
  reasoningContent?: string
  isReasoningStreaming?: boolean
  error?: string
  timestamp: number
}

function getContentFromBlocks(blocks?: MessageBlock[]) {
  return (blocks ?? [])
    .filter(block => block.type === 'text' && block.content)
    .map(block => block.content)
    .join('\n\n')
}

function mergeBlocks(
  existingBlocks?: MessageBlock[] | null,
  incomingBlocks?: MessageBlock[] | null,
  content = '',
  blockId?: string,
): MessageBlock[] {
  const existing = existingBlocks ?? []
  const incoming = incomingBlocks ?? []

  if (blockId && content) {
    const blocksMap = new Map(existing.map(block => [block.id, block]))
    const targetBlock = blocksMap.get(blockId)

    if (targetBlock?.type === 'text') {
      blocksMap.set(blockId, {
        ...targetBlock,
        content: `${targetBlock.content ?? ''}${content}`,
      })
    } else {
      blocksMap.set(blockId, {
        id: blockId,
        type: 'text',
        content,
        status: 'streaming',
        timestamp: Date.now(),
      })
    }

    return Array.from(blocksMap.values())
  }

  if (content && incoming.length === 0) {
    const blocksArray = existing.map(block => ({ ...block }))
    const lastBlock = blocksArray[blocksArray.length - 1]

    if (lastBlock?.type === 'text' && lastBlock.status === 'streaming') {
      lastBlock.content = `${lastBlock.content ?? ''}${content}`
      return blocksArray
    }

    blocksArray.push({
      id: `text-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
      type: 'text',
      content,
      status: 'streaming',
      timestamp: Date.now(),
    })
    return blocksArray
  }

  if (incoming.length === 0) {
    return existing
  }

  const blocksArray: MessageBlock[] = existing.map(block => ({
    ...block,
    status: block.type === 'text' && block.status === 'streaming'
      ? 'done'
      : block.status,
  }))
  const blocksMap = new Map(blocksArray.map(block => [block.id, block]))

  incoming.forEach(incomingBlock => {
    const existingBlock = blocksMap.get(incomingBlock.id)
    blocksMap.set(
      incomingBlock.id,
      existingBlock ? { ...existingBlock, ...incomingBlock } : incomingBlock,
    )
  })

  return Array.from(blocksMap.values())
}

function mergeDoneBlocks(
  existingBlocks?: MessageBlock[] | null,
  incomingBlocks?: MessageBlock[] | null,
): MessageBlock[] {
  const existing = existingBlocks ?? []
  const incoming = incomingBlocks ?? []

  if (existing.length === 0) return incoming
  if (incoming.length === 0) return existing

  const existingNonTextBlocks = new Map(
    existing
      .filter(block => block.type !== 'text')
      .map(block => [block.id, block]),
  )

  return incoming.map(incomingBlock => {
    if (incomingBlock.type === 'text') return incomingBlock
    const existingBlock = existingNonTextBlocks.get(incomingBlock.id)
    return existingBlock ? { ...existingBlock, ...incomingBlock } : incomingBlock
  })
}

export function useChat() {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState<number | null>(null)
  const streamingSubtaskRef = useRef<number | null>(null)
  const activeTaskIdRef = useRef<number | null>(null)

  const setCurrentTaskId = useCallback((taskId: number | null) => {
    activeTaskIdRef.current = taskId
    setActiveTaskId(taskId)
  }, [])

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

    const handleTaskCreated = (p: TaskCreatedPayload) => {
      setCurrentTaskId(p.task_id)
    }

    const handleStart = (p: ChatStartPayload) => {
      if (p.task_id) {
        setCurrentTaskId(p.task_id)
      }
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
            ? {
                ...m,
                content: m.content + p.content,
                reasoningContent:
                  p.result?.reasoning_chunk
                    ? (m.reasoningContent ?? '') + p.result.reasoning_chunk
                    : p.result?.reasoning_content ?? m.reasoningContent,
                isReasoningStreaming: Boolean(p.result?.reasoning_chunk),
                result: {
                  ...m.result,
                  ...p.result,
                  blocks: mergeBlocks(
                    m.result?.blocks,
                    p.result?.blocks,
                    p.content,
                    p.block_id,
                  ),
                  thinking: p.result?.thinking ?? m.result?.thinking,
                  reasoning_content:
                    p.result?.reasoning_content ??
                    p.result?.reasoning_chunk ??
                    m.result?.reasoning_content,
                },
              }
            : m,
        ),
      )
    }

    const handleBlockCreated = (p: ChatBlockCreatedPayload) => {
      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? {
                ...m,
                result: {
                  ...m.result,
                  blocks: mergeBlocks(m.result?.blocks, [p.block]),
                },
              }
            : m,
        ),
      )
    }

    const handleBlockUpdated = (p: ChatBlockUpdatedPayload) => {
      const mappedStatus = p.status === 'running' ? 'pending' : p.status
      const blockUpdate: MessageBlock = {
        id: p.block_id,
        ...(p.content !== undefined && { content: p.content }),
        ...(p.tool_output !== undefined && { tool_output: p.tool_output }),
        ...(p.tool_input !== undefined && { tool_input: p.tool_input }),
        ...(p.argument_status !== undefined && { argument_status: p.argument_status }),
        ...(mappedStatus !== undefined && { status: mappedStatus }),
      }

      setMessages(prev =>
        prev.map(m =>
          m.subtaskId === p.subtask_id
            ? {
                ...m,
                result: {
                  ...m.result,
                  blocks: mergeBlocks(m.result?.blocks, [blockUpdate]),
                },
              }
            : m,
        ),
      )
    }

    const handleDone = (p: ChatDonePayload) => {
      if (p.task_id) {
        setCurrentTaskId(p.task_id)
      }
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
                  getContentFromBlocks(p.result?.blocks) ||
                  m.content,
                result: {
                  ...m.result,
                  value: p.result?.value,
                  thinking: p.result?.thinking ?? m.result?.thinking,
                  reasoning_content:
                    p.result?.reasoning_content ?? m.result?.reasoning_content,
                  blocks: mergeDoneBlocks(m.result?.blocks, p.result?.blocks),
                },
                reasoningContent:
                  p.result?.reasoning_content ?? m.reasoningContent,
                isReasoningStreaming: false,
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

    socket.on(ServerEvents.TASK_CREATED, handleTaskCreated)
    socket.on(ServerEvents.CHAT_START, handleStart)
    socket.on(ServerEvents.CHAT_CHUNK, handleChunk)
    socket.on(ServerEvents.CHAT_DONE, handleDone)
    socket.on(ServerEvents.CHAT_ERROR, handleError)
    socket.on(ServerEvents.CHAT_CANCELLED, handleCancelled)
    socket.on(ServerEvents.CHAT_BLOCK_CREATED, handleBlockCreated)
    socket.on(ServerEvents.CHAT_BLOCK_UPDATED, handleBlockUpdated)

    return () => {
      socket.off(ServerEvents.TASK_CREATED, handleTaskCreated)
      socket.off(ServerEvents.CHAT_START, handleStart)
      socket.off(ServerEvents.CHAT_CHUNK, handleChunk)
      socket.off(ServerEvents.CHAT_DONE, handleDone)
      socket.off(ServerEvents.CHAT_ERROR, handleError)
      socket.off(ServerEvents.CHAT_CANCELLED, handleCancelled)
      socket.off(ServerEvents.CHAT_BLOCK_CREATED, handleBlockCreated)
      socket.off(ServerEvents.CHAT_BLOCK_UPDATED, handleBlockUpdated)
    }
  }, [setCurrentTaskId])

  // Load message history for a task
  const loadMessages = useCallback(async (taskId: number) => {
    setCurrentTaskId(taskId)
    const socket = getSocket()
    if (socket) {
      socket.emit(ClientEvents.TASK_JOIN, { task_id: taskId })
    }

    try {
      const res = await apiFetch<SubTaskListResponse>(
        `/subtasks?task_id=${taskId}&limit=100&from_latest=true`,
      )
      const history: UIMessage[] = res.items.map((st: SubTask) => {
        const blockContent = getContentFromBlocks(st.result?.blocks)
        const content =
          st.role === 'USER'
            ? st.prompt ?? ''
            : st.result?.value ?? blockContent
        return {
          id: `msg-${st.id}`,
          role: st.role === 'USER' ? 'user' : 'ai',
          content,
          status: 'completed' as const,
          subtaskId: st.id,
          messageId: st.message_id,
          botName: st.bot_name,
          result: st.result,
          reasoningContent: st.result?.reasoning_content,
          isReasoningStreaming: false,
          timestamp: new Date(st.created_at).getTime(),
        }
      })
      setMessages(history)
    } catch (e) {
      console.error('Failed to load messages', e)
    }
  }, [setCurrentTaskId])

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
        task_id: taskId ?? activeTaskIdRef.current ?? undefined,
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
    [],
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
    setCurrentTaskId(null)
    setIsStreaming(false)
  }, [activeTaskId, setCurrentTaskId])

  return {
    messages,
    isStreaming,
    activeTaskId,
    sendMessage,
    stopStream,
    loadMessages,
    clearMessages,
    setCurrentTaskId,
  }
}
