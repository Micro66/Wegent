// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import {
  clearPromptDraft,
  getPromptDraft,
  savePromptDraft,
} from '@/features/prompt-draft/utils/promptDraftStorage'

describe('promptDraftStorage feature module', () => {
  const taskId = 42

  beforeEach(() => {
    localStorage.clear()
  })

  test('save and load draft by task id', () => {
    savePromptDraft(taskId, {
      title: '会话提炼提示词',
      prompt: '你是产品协作助手，负责帮助我沉淀协作方式。',
      model: 'gpt-5.4',
      version: 1,
      createdAt: '2026-03-28T00:00:00Z',
      sourceConversationId: String(taskId),
    })

    const draft = getPromptDraft(taskId)
    expect(draft).not.toBeNull()
    expect(draft?.title).toBe('会话提炼提示词')
  })

  test('clear draft by task id', () => {
    savePromptDraft(taskId, {
      title: 'to-clear',
      prompt: '你是清理助手，负责清理。',
      model: 'gpt-5.4',
      version: 1,
      createdAt: '2026-03-28T00:00:00Z',
      sourceConversationId: String(taskId),
    })

    clearPromptDraft(taskId)
    expect(getPromptDraft(taskId)).toBeNull()
  })
})
