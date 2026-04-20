// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import React from 'react'
import { render } from '@testing-library/react'
import MessagesArea from '@/features/tasks/components/message/MessagesArea'
import { TaskStateMachine } from '@/features/tasks/state/TaskStateMachine'
import type { DisplayMessage } from '@/features/tasks/hooks/useUnifiedMessages'

const messageBubbleRenderSpy = jest.fn()

const mockMessages: DisplayMessage[] = [
  {
    id: 'ai-1',
    type: 'ai',
    content: 'Handled by beta',
    timestamp: Date.now(),
    status: 'completed',
    subtaskId: 101,
    botName: 'Agent Beta',
    botIcon: 'bot-beta-icon',
  } as DisplayMessage,
]

jest.mock('@/features/tasks/components/message/MessageBubble', () => ({
  __esModule: true,
  default: (props: unknown) => {
    messageBubbleRenderSpy(props)
    return <div data-testid="message-bubble" />
  },
}))

jest.mock('@/features/tasks/hooks/useUnifiedMessages', () => ({
  useUnifiedMessages: () => ({
    messages: mockMessages,
    streamingSubtaskIds: [],
    isStreaming: false,
  }),
}))

jest.mock('@/features/tasks/contexts/taskContext', () => ({
  useTaskContext: () => ({
    selectedTaskDetail: {
      id: 55,
      is_group_chat: true,
      teamRefs: [
        { id: 11, team_id: 11, name: 'Agent Alpha', namespace: 'default', user_id: 1 },
        { id: 22, team_id: 22, name: 'Agent Beta', namespace: 'default', user_id: 1 },
      ],
      team: { id: 11, name: 'Agent Alpha', icon: 'bot-alpha-icon' },
    },
    refreshSelectedTaskDetail: jest.fn(),
    refreshTasks: jest.fn(),
    setSelectedTask: jest.fn(),
  }),
}))

jest.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({
    toast: jest.fn(),
  }),
}))

jest.mock('@/features/theme/ThemeProvider', () => ({
  useTheme: () => ({ theme: 'light' }),
}))

jest.mock('@/features/common/UserContext', () => ({
  useUser: () => ({
    user: { id: 1, user_name: 'tester' },
  }),
}))

jest.mock('@/features/tasks/contexts/chatStreamContext', () => ({
  useChatStreamContext: () => ({
    cleanupMessagesAfterEdit: jest.fn(),
  }),
}))

jest.mock('@/hooks/useTraceAction', () => ({
  useTraceAction: () => ({
    traceAction: async (_name: string, _attrs: unknown, fn: () => Promise<void>) => fn(),
  }),
}))

jest.mock('@/features/layout/hooks/useMediaQuery', () => ({
  useIsMobile: () => false,
}))

jest.mock('@/contexts/SocketContext', () => ({
  useSocket: () => ({
    registerCorrectionHandlers: () => () => {},
  }),
}))

jest.mock('@/features/tasks/components/share/TaskShareModal', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('@/features/tasks/components/share/ExportSelectModal', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('@/features/tasks/components/group-chat', () => ({
  TaskMembersPanel: () => null,
}))

jest.mock('@/features/inbox/components/ForwardMessageDialog', () => ({
  ForwardMessageDialog: () => null,
}))

jest.mock('@/features/tasks/components/CorrectionProgressIndicator', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('@/features/tasks/components/CorrectionResultPanel', () => ({
  __esModule: true,
  default: () => null,
}))

describe('TaskStateMachine group chat identity replay', () => {
  it('preserves the replying agent name and icon across mixed-agent history replay', async () => {
    const machine = new TaskStateMachine(55, {
      joinTask: async () => ({
        subtasks: [
          {
            id: 101,
            role: 'TEAM',
            team_id: 11,
            status: 'COMPLETED',
            created_at: '2026-04-20T10:00:00.000Z',
            result: { value: 'Alpha reply' },
            message_id: 1,
          },
          {
            id: 102,
            role: 'TEAM',
            team_id: 22,
            status: 'COMPLETED',
            created_at: '2026-04-20T10:01:00.000Z',
            result: { value: 'Beta reply' },
            message_id: 2,
          },
        ],
      }),
      isConnected: () => true,
    })

    machine.setSyncOptions({
      isGroupChat: true,
      groupChatTeams: [
        { id: 11, name: 'Agent Alpha', icon: 'bot-alpha-icon' },
        { id: 22, name: 'Agent Beta', icon: 'bot-beta-icon' },
      ],
    })

    await machine.recover()

    const state = machine.getState()

    expect(state.messages.get('ai-101')?.botName).toBe('Agent Alpha')
    expect(state.messages.get('ai-101')?.botIcon).toBe('bot-alpha-icon')
    expect(state.messages.get('ai-102')?.botName).toBe('Agent Beta')
    expect(state.messages.get('ai-102')?.botIcon).toBe('bot-beta-icon')
  })
})

describe('MessagesArea group chat agent identity', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('passes the replying agent name and icon into the rendered AI message bubble', () => {
    render(
      <MessagesArea
        selectedTeam={null}
        selectedRepo={null}
        selectedBranch={null}
        isGroupChat={true}
      />
    )

    expect(messageBubbleRenderSpy).toHaveBeenCalled()
    expect(messageBubbleRenderSpy.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        msg: expect.objectContaining({
          botName: 'Agent Beta',
          botIcon: 'bot-beta-icon',
        }),
      })
    )
  })
})
