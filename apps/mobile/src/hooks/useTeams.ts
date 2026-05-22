import { useState, useEffect } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { TeamListResponse, Team } from '@/types/api'

export function useTeams() {
  const [teams, setTeams] = useState<Team[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch<TeamListResponse>('/teams?scope=personal&limit=50')
      .then(res => setTeams(res.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return { teams, loading }
}
