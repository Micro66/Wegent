// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from 'react'

import { knowledgeBaseApi } from '@/apis/knowledge-base'
import type { KnowledgeBaseDefaultRef } from '@/types/api'

interface UseKnowledgeBaseOptionsResult {
  options: KnowledgeBaseDefaultRef[]
  loading: boolean
  error: Error | null
}

export function useKnowledgeBaseOptions(): UseKnowledgeBaseOptionsResult {
  const [options, setOptions] = useState<KnowledgeBaseDefaultRef[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let cancelled = false

    const fetchKnowledgeBases = async () => {
      setLoading(true)
      setError(null)

      try {
        const response = await knowledgeBaseApi.list({ scope: 'all' })
        if (cancelled) {
          return
        }

        const nextOptions = response.items
          .map(item => ({
            id: item.id,
            name: item.name,
          }))
          .sort((left, right) => left.name.localeCompare(right.name))

        setOptions(nextOptions)
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError instanceof Error ? fetchError : new Error('Failed to fetch KBs'))
          setOptions([])
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchKnowledgeBases()

    return () => {
      cancelled = true
    }
  }, [])

  return useMemo(
    () => ({
      options,
      loading,
      error,
    }),
    [error, loading, options]
  )
}
