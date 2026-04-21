// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

import { ChatPageDesktop } from '@/app/(tasks)/chat/ChatPageDesktop'
import { CreateGroupChatDialog } from '@/features/tasks/components/group-chat/CreateGroupChatDialog'

const mockPush = jest.fn()
const mockSendMessage = jest.fn()
const mockRefreshTasks = jest.fn()
const mockSetSelectedTask = jest.fn()
const mockToast = jest.fn()
const mockTeams = [
  { id: 11, name: 'Agent Alpha', namespace: 'default', user_id: 1, agent_type: 'chat' },
  { id: 22, name: 'Agent Beta', namespace: 'default', user_id: 1, agent_type: 'chat' },
  { id: 33, name: 'Code Agent', namespace: 'default', user_id: 1, agent_type: 'code' },
]

// Mock window.matchMedia for useIsDesktop hook
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query: string) => ({
    matches: query === '(min-width: 1024px)', // Simulate desktop screen
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  useSearchParams: () => ({
    get: () => null,
  }),
}))

jest.mock('@/features/tasks/service/teamService', () => ({
  teamService: {
    useTeams: () => ({
      teams: [],
      isTeamsLoading: false,
      refreshTeams: jest.fn().mockResolvedValue([]),
    }),
  },
}))

jest.mock('@/features/layout/TopNavigation', () => ({
  __esModule: true,
  default: ({ children }: { children?: ReactNode }) => (
    <div>
      <div>top-navigation</div>
      <div>{children}</div>
    </div>
  ),
}))

jest.mock('@/features/tasks/components/sidebar', () => ({
  TaskSidebar: () => <div>task-sidebar</div>,
  ResizableSidebar: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CollapsedSidebarButtons: () => <div>collapsed-sidebar-buttons</div>,
  SearchDialog: () => <div>search-dialog</div>,
}))

jest.mock('@/features/layout/GithubStarButton', () => ({
  GithubStarButton: () => <div>github-star</div>,
}))

jest.mock('@/features/common/UserContext', () => ({
  useUser: () => ({ user: { id: 99, user_name: 'alice' } }),
}))

jest.mock('@/contexts/TeamContext', () => ({
  useTeamContext: () => ({
    teams: mockTeams,
    isTeamsLoading: false,
    refreshTeams: jest.fn().mockResolvedValue([]),
    addTeam: jest.fn(),
  }),
}))

jest.mock('@/contexts/DeviceContext', () => ({
  useDevices: () => ({
    selectedDeviceId: null,
    devices: [],
  }),
}))

jest.mock('@/features/tasks/contexts/taskContext', () => ({
  useTaskContext: () => ({
    refreshTasks: mockRefreshTasks,
    selectedTaskDetail: {
      id: 42,
      title: 'Task 42',
      team: {
        agent_type: 'chat',
        bots: [],
      },
    },
    setSelectedTask: mockSetSelectedTask,
    refreshSelectedTaskDetail: jest.fn(),
  }),
}))

jest.mock('@/features/tasks/contexts/chatStreamContext', () => ({
  useChatStreamContext: () => ({
    sendMessage: mockSendMessage,
    clearAllStreams: jest.fn(),
  }),
}))

jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}))

jest.mock('@/features/tasks/hooks/useSearchShortcut', () => ({
  useSearchShortcut: () => ({
    shortcutDisplayText: 'Ctrl+K',
  }),
}))

jest.mock('@/features/tasks/components/chat', () => ({
  ChatArea: () => <div>chat-area</div>,
}))

jest.mock('@/features/tasks/components/group-chat', () => ({
  CreateGroupChatDialog: () => <div>create-group-chat-dialog</div>,
}))

jest.mock('@/features/tasks/components/selector', () => ({
  ModelSelector: ({
    setSelectedModel,
    selectedModel,
  }: {
    setSelectedModel: (model: { name: string }) => void
    selectedModel?: { name?: string }
  }) => (
    <button
      type="button"
      data-testid={`mock-model-selector-${selectedModel?.name || 'default'}`}
      onClick={() => setSelectedModel({ name: 'gpt-4.1' })}
    >
      choose-model
    </button>
  ),
}))

// Mock EnhancedMarkdown and other ESM-heavy components to avoid Jest ESM issues
jest.mock('@/components/common/EnhancedMarkdown', () => ({
  __esModule: true,
  default: ({ children }: { children?: string }) => (
    <div data-testid="enhanced-markdown">{children}</div>
  ),
  CodeBlock: ({ children }: { children?: string }) => (
    <pre data-testid="code-block">{children}</pre>
  ),
}))

jest.mock('@/features/tasks/components/message', () => ({
  MessageBubble: ({ content }: { content?: string }) => (
    <div data-testid="message-bubble">{content}</div>
  ),
  MessageSkeleton: () => <div data-testid="message-skeleton">Loading...</div>,
  WelcomeMessage: () => <div data-testid="welcome-message">Welcome</div>,
}))

jest.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

jest.mock('@/features/tasks/components/remote-workspace', () => ({
  RemoteWorkspaceEntry: ({
    taskId,
    forceDisabled,
  }: {
    taskId?: number | null
    forceDisabled?: boolean
  }) => (
    <div data-testid="remote-workspace-entry">{`${String(taskId)}:${String(!!forceDisabled)}`}</div>
  ),
}))

describe('ChatPageDesktop remote workspace integration', () => {
  beforeEach(() => {
    mockPush.mockReset()
    mockSendMessage.mockReset()
    mockSendMessage.mockResolvedValue(undefined)
    mockRefreshTasks.mockReset()
    mockSetSelectedTask.mockReset()
    mockToast.mockReset()
  })

  test('chat desktop renders remote workspace entry in top nav when task selected', () => {
    render(<ChatPageDesktop />)

    expect(screen.getByTestId('remote-workspace-entry')).toHaveTextContent('42:false')
  })

  test('group chat create dialog submits multi-agent config and edited history window', () => {
    render(<CreateGroupChatDialog open={true} onOpenChange={jest.fn()} />)

    fireEvent.change(screen.getByTestId('group-chat-title-input'), {
      target: { value: 'Release War Room' },
    })
    fireEvent.click(screen.getByTestId('group-chat-agent-checkbox-11'))
    fireEvent.click(screen.getByTestId('group-chat-agent-checkbox-22'))
    fireEvent.change(screen.getByTestId('group-chat-history-days-input'), {
      target: { value: '7' },
    })
    fireEvent.change(screen.getByTestId('group-chat-history-messages-input'), {
      target: { value: '99' },
    })
    // Click model selector for each selected agent (2 agents selected)
    const modelSelectors = screen.getAllByTestId(/mock-model-selector/)
    modelSelectors.forEach(selector => {
      fireEvent.click(selector)
    })
    fireEvent.click(screen.getByTestId('group-chat-create-button'))

    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Release War Room',
        team_id: 11,
        is_group_chat: true,
        teamRefs: [
          {
            id: 11,
            team_id: 11,
            name: 'Agent Alpha',
            namespace: 'default',
            user_id: 1,
            model_id: 'gpt-4.1',
            force_override_bot_model: false,
          },
          {
            id: 22,
            team_id: 22,
            name: 'Agent Beta',
            namespace: 'default',
            user_id: 1,
            model_id: 'gpt-4.1',
            force_override_bot_model: false,
          },
        ],
        groupChatConfig: {
          historyWindow: {
            maxDays: 7,
            maxMessages: 99,
          },
        },
      }),
      expect.any(Object)
    )
  })
})
