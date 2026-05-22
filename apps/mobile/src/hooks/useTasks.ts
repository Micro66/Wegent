import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/lib/api-client'
import type { TaskListResponse, Task } from '@/types/api'

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  const loadTaskItems = useCallback(async () => {
    const res = await apiFetch<TaskListResponse>('/tasks/lite/personal?limit=50')
    return res.items
  }, [])

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      setTasks(await loadTaskItems())
    } catch (error) {
      console.error(error)
    } finally {
      setLoading(false)
    }
  }, [loadTaskItems])

  useEffect(() => {
    let ignore = false

    loadTaskItems()
      .then((items) => {
        if (!ignore) {
          setTasks(items)
        }
      })
      .catch(console.error)
      .finally(() => {
        if (!ignore) {
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [loadTaskItems])

  const createTask = useCallback(async (teamId: number, message: string): Promise<number> => {
    const { task_id } = await apiFetch<{ task_id: number }>('/tasks', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    await apiFetch(`/tasks/${task_id}`, {
      method: 'PUT',
      body: JSON.stringify({ team_id: teamId, title: message.slice(0, 50), prompt: message }),
    })
    fetchTasks()
    return task_id
  }, [fetchTasks])

  return { tasks, loading, createTask, refetch: fetchTasks }
}
