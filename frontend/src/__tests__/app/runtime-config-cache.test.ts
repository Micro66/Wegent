/** @jest-environment node */

// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { GET } from '@/app/runtime-config/route'
import { clearRuntimeConfigCache, fetchRuntimeConfig } from '@/lib/runtime-config'

describe('runtime config caching', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    clearRuntimeConfigCache()
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        apiUrl: '',
        socketDirectUrl: '',
        enableChatContext: true,
        loginMode: 'all',
        oidcLoginText: '',
        enableDisplayQuotas: false,
        enableWiki: true,
        enableCodeKnowledgeAddRepo: true,
        vscodeLinkTemplate: '',
        feedbackUrl: 'https://github.com/wecode-ai/wegent/issues/new',
        docsUrl: 'https://wecode-ai.github.io/wegent-docs',
        otelEnabled: false,
        otelServiceName: 'wegent-frontend',
        otelCollectorEndpoint: 'http://localhost:4318',
        bindGroupDesc: '',
        bindGroupSteps: '{"variables":{"botName":"机器人"},"steps":[]}',
      }),
    }) as typeof fetch
  })

  afterEach(() => {
    jest.clearAllMocks()
    clearRuntimeConfigCache()
  })

  afterAll(() => {
    global.fetch = originalFetch
  })

  test('fetchRuntimeConfig bypasses browser cache', async () => {
    await fetchRuntimeConfig()

    expect(global.fetch).toHaveBeenCalledWith('/runtime-config', {
      cache: 'no-store',
    })
  })

  test('runtime config route returns no-store cache headers', async () => {
    const response = await GET()

    expect(response.headers.get('Cache-Control')).toBe('no-store, max-age=0')
  })
})
