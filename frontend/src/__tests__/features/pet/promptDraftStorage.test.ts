// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import {
  clearPromptDraft,
  getPromptDraft,
  savePromptDraft,
} from '@/features/pet/utils/promptDraftStorage'

describe('promptDraftStorage', () => {
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
    expect(draft?.prompt.startsWith('你是')).toBe(true)
  })

  test('overwrite existing draft for same task id', () => {
    savePromptDraft(taskId, {
      title: 'v1',
      prompt: '你是A助手，负责A。',
      model: 'm1',
      version: 1,
      createdAt: '2026-03-28T00:00:00Z',
      sourceConversationId: String(taskId),
    })
    savePromptDraft(taskId, {
      title: 'v2',
      prompt: '你是B助手，负责B。',
      model: 'm2',
      version: 2,
      createdAt: '2026-03-28T01:00:00Z',
      sourceConversationId: String(taskId),
    })

    const draft = getPromptDraft(taskId)
    expect(draft?.title).toBe('v2')
    expect(draft?.version).toBe(2)
    expect(draft?.model).toBe('m2')
  })

  test('returns null and clears corrupted payload', () => {
    localStorage.setItem('pet:prompt-draft:42', '{bad json')

    const draft = getPromptDraft(taskId)
    expect(draft).toBeNull()
    expect(localStorage.getItem('pet:prompt-draft:42')).toBeNull()
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
