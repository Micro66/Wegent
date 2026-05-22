import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { UnifiedModelListResponse, UnifiedModel } from '@/types/api'

export function useModels(shellType: string = 'Chat') {
  const [models, setModels] = useState<UnifiedModel[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch<UnifiedModelListResponse>(`/models/unified?shell_type=${shellType}`)
      .then(res => setModels((res.data ?? []).filter(m => m.modelCategoryType === 'llm')))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [shellType])

  return { models, loading }
}
