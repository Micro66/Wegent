import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/lib/api-client'
import { setToken, removeToken, isAuthenticated } from '@/lib/token-store'
import type { User } from '@/types/api'

interface AuthState {
  user: User | null
  loading: boolean
  error: string | null
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  })

  const fetchUser = useCallback(async () => {
    if (!isAuthenticated()) {
      setState({ user: null, loading: false, error: null })
      return
    }
    try {
      const user = await apiFetch<User>('/users/me')
      setState({ user, loading: false, error: null })
    } catch {
      removeToken()
      setState({ user: null, loading: false, error: 'Session expired' })
    }
  }, [])

  useEffect(() => { fetchUser() }, [fetchUser])

  const login = useCallback(async (username: string, password: string) => {
    setState(s => ({ ...s, loading: true, error: null }))
    try {
      const data = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_name: username, password }),
      }).then(r => {
        if (!r.ok) throw new Error('Login failed')
        return r.json()
      })
      // Backend returns token; extract and store
      const token = data.token || data.access_token
      if (!token) throw new Error('No token in response')
      setToken(token)
      const user = await apiFetch<User>('/users/me')
      setState({ user, loading: false, error: null })
    } catch (e) {
      setState(s => ({ ...s, loading: false, error: (e as Error).message }))
    }
  }, [])

  const logout = useCallback(() => {
    removeToken()
    setState({ user: null, loading: false, error: null })
  }, [])

  return { ...state, login, logout, refetch: fetchUser }
}
