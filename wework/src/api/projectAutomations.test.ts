import { describe, expect, test, vi } from 'vitest'
import type { HttpClient } from './http'
import { createProjectAutomationApi } from './projectAutomations'

describe('createProjectAutomationApi', () => {
  test('maps the snake-case notification channel contract for the automation editor', async () => {
    const client = {
      get: vi.fn().mockResolvedValue([
        {
          id: 19,
          name: 'Feedback bot',
          channel_type: 'dingtalk',
          is_bound: false,
        },
      ]),
    } as unknown as HttpClient

    const channels = await createProjectAutomationApi(client).listDingTalkChannels()

    expect(client.get).toHaveBeenCalledWith('/users/me/available-channels')
    expect(channels).toEqual([
      {
        id: 19,
        name: 'Feedback bot',
        channelType: 'dingtalk',
        isBound: false,
      },
    ])
  })
})
