// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

const KEY_PREFIX = 'pet:prompt-draft:'

export interface PromptDraftLocal {
  title: string
  prompt: string
  model: string
  version: number
  createdAt: string
  sourceConversationId: string
}

function getStorageKey(conversationId: string | number): string {
  return `${KEY_PREFIX}${conversationId}`
}

export function savePromptDraft(conversationId: string | number, draft: PromptDraftLocal): void {
  try {
    localStorage.setItem(getStorageKey(conversationId), JSON.stringify(draft))
  } catch {
    // Keep UI non-blocking when storage is unavailable.
  }
}

export function getPromptDraft(conversationId: string | number): PromptDraftLocal | null {
  try {
    const raw = localStorage.getItem(getStorageKey(conversationId))
    if (!raw) return null
    return JSON.parse(raw) as PromptDraftLocal
  } catch {
    try {
      localStorage.removeItem(getStorageKey(conversationId))
    } catch {
      // ignore cleanup failure
    }
    return null
  }
}

export function clearPromptDraft(conversationId: string | number): void {
  try {
    localStorage.removeItem(getStorageKey(conversationId))
  } catch {
    // Keep UI non-blocking when storage is unavailable.
  }
}
