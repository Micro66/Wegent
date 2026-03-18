// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Task Health Check Hook
 *
 * This hook monitors task health by periodically checking the backend
 * for orphaned tasks (database shows RUNNING but no active stream in Redis).
 *
 * When an orphaned task is detected, it automatically marks the task as failed
 * in the frontend state and notifies the user.
 *
 * Configuration via environment variables:
 * - NEXT_PUBLIC_HEALTH_CHECK_ENABLED: Enable/disable health checks (default: true)
 * - NEXT_PUBLIC_HEALTH_CHECK_INTERVAL_MS: Check interval in milliseconds (default: 30000)
 */

import { useEffect, useRef, useCallback } from 'react'
import { taskApis } from '@/apis/tasks'
import { TaskDetailSubtask } from '@/types/api'
import { useToast } from '@/hooks/use-toast'
import { useTaskContext } from '@/features/tasks/contexts/taskContext'
import { taskStateManager } from '../state'

// Default configuration value
const DEFAULT_HEALTH_CHECK_INTERVAL_MS = 30000

export interface UseTaskHealthCheckOptions {
  /** Whether to enable auto-cleanup of orphaned tasks */
  autoCleanup?: boolean
  /** Custom interval in milliseconds (overrides env var) */
  intervalMs?: number
  /** Callback when orphaned task is detected */
  onOrphanedDetected?: (taskId: number, staleDurationSeconds: number | null) => void
}

// Global configuration cache
let cachedEnabled: boolean | null = null
let cachedIntervalMs: number | null = null

/**
 * Get environment configuration (cached after first call)
 */
const getEnvConfig = () => {
  if (cachedEnabled !== null && cachedIntervalMs !== null) {
    return { enabled: cachedEnabled, intervalMs: cachedIntervalMs }
  }

  // Access environment variables (Next.js exposes these at build time)
  const enabled = process.env.NEXT_PUBLIC_HEALTH_CHECK_ENABLED !== 'false'
  const intervalMs = parseInt(
    process.env.NEXT_PUBLIC_HEALTH_CHECK_INTERVAL_MS || String(DEFAULT_HEALTH_CHECK_INTERVAL_MS),
    10
  )

  cachedEnabled = enabled
  cachedIntervalMs = intervalMs

  return { enabled, intervalMs }
}

/**
 * Hook to monitor task health and detect orphaned tasks
 *
 * @param taskId - Task ID to monitor
 * @param subtasks - Current subtasks for the task
 * @param options - Optional configuration
 */
export function useTaskHealthCheck(
  taskId: number | null | undefined,
  subtasks: TaskDetailSubtask[],
  options: UseTaskHealthCheckOptions = {}
) {
  const { toast } = useToast()
  const { refreshSelectedTaskDetail } = useTaskContext()
  const { autoCleanup = true, intervalMs, onOrphanedDetected } = options

  // Use refs to avoid re-triggering effect
  const processedOrphanedRef = useRef<Set<number>>(new Set())
  const { enabled: envEnabled, intervalMs: envIntervalMs } = getEnvConfig()
  const actualIntervalMs = intervalMs ?? envIntervalMs

  /**
   * Format duration in seconds to human readable string
   */
  const formatDuration = useCallback((seconds: number | null): string => {
    if (seconds === null) return ''
    if (seconds < 60) return `${seconds}秒`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟`
    return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分钟`
  }, [])

  /**
   * Check task health and handle orphaned state
   */
  const checkHealth = useCallback(async () => {
    if (!taskId || !envEnabled) return

    // Only check tasks with running subtasks
    const runningSubtasks = subtasks.filter(
      st => st.role === 'ASSISTANT' && st.status === 'RUNNING'
    )

    if (runningSubtasks.length === 0) {
      // Clear processed set when no running subtasks
      processedOrphanedRef.current.delete(taskId)
      return
    }

    try {
      const health = await taskApis.getTaskHealth(taskId)

      if (health.orphaned && !processedOrphanedRef.current.has(taskId)) {
        // Mark as processed to avoid duplicate handling
        processedOrphanedRef.current.add(taskId)

        // Call optional callback
        onOrphanedDetected?.(taskId, health.stale_duration_seconds)

        // Auto-cleanup: call backend API to mark as FAILED in database
        if (autoCleanup) {
          try {
            const cleanupResult = await taskApis.cleanupOrphanedTask(taskId)
            console.log('[useTaskHealthCheck] Cleanup result:', cleanupResult)

            // Mark task as failed in state machine
            const machine = taskStateManager.get(taskId)
            if (machine) {
              // Mark each running subtask as failed
              runningSubtasks.forEach(subtask => {
                machine.handleChatError(
                  subtask.id,
                  `任务已异常终止（已死亡 ${formatDuration(health.stale_duration_seconds)}）`
                )
              })
            }

            // Show toast notification
            toast({
              title: '检测到任务异常',
              description: `任务已异常终止（已死亡 ${formatDuration(health.stale_duration_seconds)}），已自动清理状态`,
              variant: 'default',
            })

            // Refresh task detail to get updated status from backend
            refreshSelectedTaskDetail(false)
          } catch (error) {
            console.error('[useTaskHealthCheck] Failed to cleanup orphaned task:', error)
          }
        }
      } else if (!health.orphaned) {
        // Clear processed flag if task is no longer orphaned
        processedOrphanedRef.current.delete(taskId)
      }
    } catch (error) {
      // Silent fail - health check is best effort
      console.warn('[useTaskHealthCheck] Health check failed:', error)
    }
  }, [
    taskId,
    subtasks,
    autoCleanup,
    formatDuration,
    onOrphanedDetected,
    refreshSelectedTaskDetail,
    toast,
    envEnabled,
  ])

  // Set up periodic health checks
  useEffect(() => {
    if (!taskId || !envEnabled) return

    // Check immediately on mount/subtasks change
    checkHealth()

    // Set up interval
    const interval = setInterval(checkHealth, actualIntervalMs)

    return () => {
      clearInterval(interval)
    }
  }, [taskId, subtasks, checkHealth, actualIntervalMs, envEnabled])

  /**
   * Manual health check function
   */
  const manualCheck = useCallback(async (): Promise<boolean> => {
    if (!taskId) return false

    try {
      const health = await taskApis.getTaskHealth(taskId)
      return !health.orphaned
    } catch (error) {
      console.warn('[useTaskHealthCheck] Manual health check failed:', error)
      return true // Assume healthy on error to avoid false alarms
    }
  }, [taskId])

  return {
    checkHealth: manualCheck,
    isEnabled: envEnabled,
    intervalMs: actualIntervalMs,
  }
}

/**
 * Hook to check task health before stopping a stream
 * Used in stopStream to detect if task is already dead
 */
export function useHealthCheckBeforeStop() {
  /**
   * Check if task is healthy before attempting to stop
   * @param taskId - Task ID
   * @returns Object with isHealthy flag and health data
   */
  const checkBeforeStop = useCallback(async (taskId: number) => {
    const { enabled } = getEnvConfig()
    if (!enabled) {
      return { isHealthy: true, isOrphaned: false, health: null }
    }

    try {
      const health = await taskApis.getTaskHealth(taskId)
      console.log('[useHealthCheckBeforeStop] Health check result:', {
        taskId,
        status: health.status,
        orphaned: health.orphaned,
        running_subtasks_count: health.running_subtasks_count,
        active_streams_count: health.active_streams_count,
      })
      return {
        isHealthy: health.status === 'healthy',
        isOrphaned: health.orphaned,
        health,
      }
    } catch (error) {
      // On error, assume healthy to not block stop operation
      console.warn('[useHealthCheckBeforeStop] Health check failed:', error)
      return { isHealthy: true, isOrphaned: false, health: null }
    }
  }, [])

  return { checkBeforeStop }
}
