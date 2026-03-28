// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { modelApis } from '@/apis/models'
import { taskApis } from '@/apis/tasks'
import { PromptDraftDialog } from '@/features/pet/components/PromptDraftDialog'

jest.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

jest.mock('@/features/prompt-tune/components/PromptFineTuneDialog', () => ({
  __esModule: true,
  default: () => null,
}))

jest.mock('@/apis/tasks', () => ({
  taskApis: {
    generatePromptDraft: jest.fn(),
    generatePromptDraftStream: jest.fn(),
  },
}))

jest.mock('@/apis/models', () => ({
  modelApis: {
    getUnifiedModels: jest.fn(),
  },
}))

describe('PromptDraftDialog', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('generates prompt draft and renders returned title and prompt', async () => {
    ;(modelApis.getUnifiedModels as jest.Mock).mockResolvedValue({
      data: [
        {
          name: 'gpt-5.4',
          type: 'public',
          displayName: 'GPT-5.4',
          provider: 'openai',
        },
      ],
    })
    ;(taskApis.generatePromptDraftStream as jest.Mock).mockResolvedValue({
      title: '会话提炼提示词',
      prompt: '你是产品协作助手，负责帮助我沉淀协作方式。',
      model: 'gpt-5.4',
      version: 1,
      created_at: '2026-03-28T00:00:00Z',
    })

    render(<PromptDraftDialog open={true} onOpenChange={() => {}} taskId={1} />)

    await waitFor(() => {
      expect(modelApis.getUnifiedModels).toHaveBeenCalledWith(
        undefined,
        false,
        'all',
        undefined,
        'llm'
      )
    })

    fireEvent.click(screen.getByTestId('prompt-draft-generate-button'))

    await waitFor(() => {
      expect(taskApis.generatePromptDraftStream).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ source: 'pet_panel' }),
        expect.any(Object)
      )
    })

    expect(await screen.findByText('会话提炼提示词')).toBeInTheDocument()
    expect(screen.getByText(/你是产品协作助手/)).toBeInTheDocument()
  })

  test('disables generate when task id is absent', async () => {
    ;(modelApis.getUnifiedModels as jest.Mock).mockResolvedValue({ data: [] })
    render(<PromptDraftDialog open={true} onOpenChange={() => {}} taskId={null} />)
    await waitFor(() => {
      expect(modelApis.getUnifiedModels).toHaveBeenCalledWith(
        undefined,
        false,
        'all',
        undefined,
        'llm'
      )
    })
    expect(screen.getByTestId('prompt-draft-generate-button')).toBeDisabled()
  })

  test('isolates draft content by conversation', async () => {
    ;(modelApis.getUnifiedModels as jest.Mock).mockResolvedValue({ data: [] })
    ;(taskApis.generatePromptDraftStream as jest.Mock).mockResolvedValue({
      title: '会话A标题',
      prompt: '会话A提示词',
      model: 'gpt-5.4',
      version: 1,
      created_at: '2026-03-28T00:00:00Z',
    })

    const { rerender } = render(
      <PromptDraftDialog open={true} onOpenChange={() => {}} taskId={1} />
    )

    fireEvent.click(screen.getByTestId('prompt-draft-generate-button'))
    expect(await screen.findByText('会话A标题')).toBeInTheDocument()

    rerender(<PromptDraftDialog open={true} onOpenChange={() => {}} taskId={2} />)

    await waitFor(() => {
      expect(screen.queryByText('会话A标题')).not.toBeInTheDocument()
    })
  })
})
