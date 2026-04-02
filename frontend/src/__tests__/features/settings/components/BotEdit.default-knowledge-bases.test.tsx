// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'

import BotEdit from '@/features/settings/components/BotEdit'
import { botApis } from '@/apis/bots'
import { knowledgeBaseApi } from '@/apis/knowledge-base'
import { modelApis } from '@/apis/models'
import { shellApis } from '@/apis/shells'
import { fetchUnifiedSkillsList } from '@/apis/skills'

jest.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

jest.mock('@/apis/knowledge-base', () => ({
  knowledgeBaseApi: {
    list: jest.fn(),
  },
}))

jest.mock('@/apis/bots', () => {
  const actual = jest.requireActual('@/apis/bots')
  return {
    ...actual,
    botApis: {
      ...actual.botApis,
      updateBot: jest.fn(),
      createBot: jest.fn(),
    },
  }
})

jest.mock('@/apis/models', () => ({
  modelApis: {
    getUnifiedModels: jest.fn(),
  },
}))

jest.mock('@/apis/shells', () => ({
  shellApis: {
    getUnifiedShells: jest.fn(),
  },
}))

jest.mock('@/apis/skills', () => ({
  fetchUnifiedSkillsList: jest.fn(),
  fetchPublicSkillsList: jest.fn(),
}))

jest.mock('@/features/settings/components/McpConfigSection', () => {
  function MockMcpConfigSection() {
    return <div data-testid="mcp-config-section" />
  }

  return MockMcpConfigSection
})
jest.mock('@/features/settings/components/skills/SkillManagementModal', () => {
  function MockSkillManagementModal() {
    return null
  }

  return MockSkillManagementModal
})
jest.mock('@/features/settings/components/skills/RichSkillSelector', () => ({
  RichSkillSelector: function MockRichSkillSelector() {
    return <div data-testid="rich-skill-selector" />
  },
}))
jest.mock('@/features/settings/components/DifyBotConfig', () => {
  function MockDifyBotConfig() {
    return null
  }

  return MockDifyBotConfig
})
jest.mock('@/features/prompt-tune/components/PromptFineTuneDialog', () => {
  function MockPromptFineTuneDialog() {
    return null
  }

  return MockPromptFineTuneDialog
})

jest.mock('@/components/ui/select', () => ({
  Select: ({
    children,
    disabled,
  }: {
    value?: string
    onValueChange?: (value: string) => void
    children: ReactNode
    disabled?: boolean
  }) => (
    <div data-testid="mock-select" data-disabled={disabled ? 'true' : 'false'}>
      {children}
    </div>
  ),
  SelectTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <div data-testid={`mock-select-item-${value}`}>{children}</div>
  ),
}))

jest.mock('@/components/ui/switch', () => ({
  Switch: ({
    checked,
    onCheckedChange,
    disabled,
  }: {
    checked?: boolean
    onCheckedChange?: (checked: boolean) => void
    disabled?: boolean
  }) => (
    <input
      data-testid="mock-switch"
      type="checkbox"
      checked={checked}
      onChange={event => onCheckedChange?.(event.target.checked)}
      disabled={disabled}
    />
  ),
}))

const mockedUpdateBot = botApis.updateBot as jest.Mock
const mockedKnowledgeBaseList = knowledgeBaseApi.list as jest.Mock
const mockedGetUnifiedModels = modelApis.getUnifiedModels as jest.Mock
const mockedGetUnifiedShells = shellApis.getUnifiedShells as jest.Mock
const mockedFetchUnifiedSkillsList = fetchUnifiedSkillsList as jest.Mock

function renderBotEdit() {
  const bot = {
    id: 7,
    name: 'Bot Alpha',
    namespace: 'default',
    shell_name: 'ClaudeCode',
    shell_type: 'ClaudeCode',
    agent_config: {
      bind_model: 'gpt-4.1',
      bind_model_type: 'public',
    },
    system_prompt: 'helpful',
    mcp_servers: {},
    skills: [],
    default_knowledge_base_refs: [{ id: 101, name: 'Product Docs' }],
    is_active: true,
    created_at: '2026-04-02T00:00:00Z',
    updated_at: '2026-04-02T00:00:00Z',
  }

  const setBots = jest.fn()
  const onClose = jest.fn()
  const toast = jest.fn()

  render(
    <BotEdit
      bots={[bot]}
      setBots={setBots}
      editingBotId={7}
      cloningBot={null}
      onClose={onClose}
      toast={toast}
      scope="personal"
    />
  )

  return { setBots, onClose, toast }
}

describe('BotEdit default knowledge bases', () => {
  beforeEach(() => {
    mockedUpdateBot.mockReset()
    mockedKnowledgeBaseList.mockReset()
    mockedGetUnifiedModels.mockReset()
    mockedGetUnifiedShells.mockReset()
    mockedFetchUnifiedSkillsList.mockReset()

    mockedGetUnifiedShells.mockResolvedValue({
      data: [{ name: 'ClaudeCode', type: 'public', shellType: 'ClaudeCode' }],
    })
    mockedGetUnifiedModels.mockResolvedValue({
      data: [{ name: 'gpt-4.1', type: 'public', namespace: 'default' }],
    })
    mockedFetchUnifiedSkillsList.mockResolvedValue([])
    mockedKnowledgeBaseList.mockResolvedValue({
      total: 2,
      items: [
        {
          id: 101,
          name: 'Product Docs',
          description: 'Product references',
          user_id: 7,
          namespace: 'default',
          document_count: 3,
          is_active: true,
          summary_enabled: false,
          max_calls_per_conversation: 5,
          exempt_calls_before_check: 0,
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
        },
        {
          id: 202,
          name: 'Runbooks',
          description: 'Ops guides',
          user_id: 7,
          namespace: 'default',
          document_count: 4,
          is_active: true,
          summary_enabled: false,
          max_calls_per_conversation: 5,
          exempt_calls_before_check: 0,
          created_at: '2026-04-02T00:00:00Z',
          updated_at: '2026-04-02T00:00:00Z',
        },
      ],
    })
    mockedUpdateBot.mockResolvedValue({
      id: 7,
      name: 'Bot Alpha',
      namespace: 'default',
      shell_name: 'ClaudeCode',
      shell_type: 'ClaudeCode',
      agent_config: {
        bind_model: 'gpt-4.1',
        bind_model_type: 'public',
      },
      system_prompt: 'helpful',
      mcp_servers: {},
      skills: [],
      default_knowledge_base_refs: [{ id: 101, name: 'Product Docs' }],
      is_active: true,
      created_at: '2026-04-02T00:00:00Z',
      updated_at: '2026-04-02T00:00:00Z',
    })
  })

  test('loads existing bot default knowledge bases into the form', async () => {
    renderBotEdit()

    expect(await screen.findByTestId('default-knowledge-base-chip-101')).toBeInTheDocument()
    expect(screen.getByText('Product Docs')).toBeInTheDocument()
  })

  test('allows adding and removing multiple knowledge bases', async () => {
    renderBotEdit()

    const searchInput = await screen.findByTestId('default-knowledge-base-search-input')
    fireEvent.change(searchInput, { target: { value: 'Runbooks' } })

    fireEvent.click(await screen.findByTestId('default-knowledge-base-option-202'))

    expect(screen.getByTestId('default-knowledge-base-chip-101')).toBeInTheDocument()
    expect(screen.getByTestId('default-knowledge-base-chip-202')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('default-knowledge-base-remove-101'))

    await waitFor(() => {
      expect(screen.queryByTestId('default-knowledge-base-chip-101')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('default-knowledge-base-chip-202')).toBeInTheDocument()
  })

  test('includes default_knowledge_base_refs in save payload', async () => {
    renderBotEdit()

    const searchInput = await screen.findByTestId('default-knowledge-base-search-input')
    fireEvent.change(searchInput, { target: { value: 'Runbooks' } })
    fireEvent.click(await screen.findByTestId('default-knowledge-base-option-202'))

    fireEvent.click(screen.getByTestId('save-button'))

    await waitFor(() => {
      expect(mockedUpdateBot).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          default_knowledge_base_refs: [
            { id: 101, name: 'Product Docs' },
            { id: 202, name: 'Runbooks' },
          ],
        })
      )
    })
  })
})
