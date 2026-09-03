import type { HttpClient } from './http'
import type { LocalLoopItemExecution } from './local/localDelivery'
import type { ProjectWorkflowDefinition } from './deliveries'

export type ProjectAutomationRunStatus =
  | 'pending'
  | 'queued'
  | 'waiting_runtime'
  | 'waiting_device'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled'

interface ProjectAutomationRuleBase {
  id: string
  projectId: string
  name: string
  prompt: string
  triggerType: 'schedule' | 'event' | 'workflow'
  eventType: 'task.created' | 'task.status_changed' | null
  eventConfig: Record<string, unknown>
  eventSource?: 'issue' | 'dingtalk'
  dingtalkChannelId?: number | null
  dingtalkBinding?: ProjectAutomationDingTalkBinding | null
  webhookEventId: string | null
  webhookSecret: string | null
  cronExpression: string | null
  timezone: string
  agentName: string
  enabled: boolean
  nextRunAt: string | null
  lastRunAt: string | null
  lastRunStatus: ProjectAutomationRunStatus | null
  version: number
  createdAt: string
  updatedAt: string
  roleSource?: 'generic' | 'agent'
  runtimeSource?: 'agent_default' | 'fixed_profile' | 'issue_creator' | 'runtime_user'
  runtimeProfileId?: string | null
  runtimeUserId?: number | null
}

export interface ProjectAutomationRule extends ProjectAutomationRuleBase {
  assignmentMode: 'manual' | 'ai_managed'
  managerType: 'custom' | 'wegent' | null
  agentId: string | null
  wegentTeamId: number | null
  model: string | null
  executionEnvironment: 'local' | 'cloud' | 'managed'
  executionDeviceId: string | null
}

export interface ProjectAutomationRun {
  id: string
  automationId: string
  projectId: string
  trigger: 'scheduled' | 'manual' | 'event'
  status: ProjectAutomationRunStatus
  timezone: string
  scheduledFor: string
  expiresAt: string | null
  taskId: string | null
  taskTitle?: string | null
  backendTaskId: number | null
  deviceId: string | null
  error: string | null
  createdAt: string
  updatedAt: string
  completedAt: string | null
  retryable?: boolean
}

interface ProjectAutomationInputBase {
  name: string
  prompt: string
  triggerType: 'schedule' | 'event' | 'workflow'
  eventType: 'task.created' | 'task.status_changed' | null
  eventConfig: Record<string, unknown>
  eventSource: 'issue' | 'dingtalk'
  dingtalkChannelId: number | null
  cronExpression: string | null
  timezone: string
  enabled: boolean
  roleSource?: 'generic' | 'agent'
  runtimeSource?: 'agent_default' | 'fixed_profile' | 'issue_creator' | 'runtime_user'
  runtimeProfileId?: string | null
  runtimeUserId?: number | null
}

export interface ProjectAutomationDingTalkBinding {
  status: 'unbound' | 'pairing' | 'bound'
  conversationTitle: string | null
  boundAt: string | null
  expiresAt: string | null
}

export interface AutomationDingTalkChannel {
  id: number
  name: string
  channelType: string
  isBound: boolean
}

interface AutomationDingTalkChannelResponse {
  id: number
  name: string
  channel_type: string
  is_bound: boolean
}

export interface ProjectAutomationInput extends ProjectAutomationInputBase {
  assignmentMode: 'manual' | 'ai_managed'
  managerType: 'custom' | 'wegent' | null
  agentId: string | null
  wegentTeamId: number | null
  model: string | null
  executionEnvironment: 'local' | 'cloud' | null
  executionDeviceId: string | null
}

export interface ProjectAutomationWorkflowMigrationResult {
  automation: ProjectAutomationRule
  projectVersion: number
  workflowAutomationId: string
}

export interface ProjectAutomationDeleteResult {
  projectVersion: number
  workflowAutomationId: string | null
}

export function createProjectAutomationApi(client: HttpClient) {
  return {
    heartbeat(
      execution: Pick<LocalLoopItemExecution, 'id' | 'cloud_project_id'>,
      runtimeDeviceId: string | null,
      runtimeTaskId: string | null,
      leaseSeconds = 300
    ) {
      return client.post<LocalLoopItemExecution | null>(
        `/v1/cloud-projects/${execution.cloud_project_id}/executions/${execution.id}/heartbeat`,
        {
          runtime_device_id: runtimeDeviceId,
          runtime_task_id: runtimeTaskId,
          lease_seconds: leaseSeconds,
        }
      )
    },
    startRequested(
      execution: Pick<LocalLoopItemExecution, 'id' | 'cloud_project_id'>,
      runtimeDeviceId: string,
      runtimeTaskId: string
    ) {
      return client.post<LocalLoopItemExecution | null>(
        `/v1/cloud-projects/${execution.cloud_project_id}/executions/${execution.id}/start-requested`,
        {
          runtime_device_id: runtimeDeviceId,
          runtime_task_id: runtimeTaskId,
        }
      )
    },
    dispatchUnknown(
      execution: Pick<LocalLoopItemExecution, 'id' | 'cloud_project_id'>,
      runtimeDeviceId: string,
      runtimeTaskId: string,
      error: string
    ) {
      return client.post<LocalLoopItemExecution | null>(
        `/v1/cloud-projects/${execution.cloud_project_id}/executions/${execution.id}/dispatch-unknown`,
        {
          runtime_device_id: runtimeDeviceId,
          runtime_task_id: runtimeTaskId,
          error,
        }
      )
    },
    runtimeStart(
      execution: Pick<LocalLoopItemExecution, 'id' | 'cloud_project_id'>,
      runtimeDeviceId: string,
      runtimeTaskId: string,
      prompt: string | null,
      model?: string | null
    ) {
      return client.post<LocalLoopItemExecution | null>(
        `/v1/cloud-projects/${execution.cloud_project_id}/executions/${execution.id}/runtime-start`,
        {
          runtime_device_id: runtimeDeviceId,
          runtime_task_id: runtimeTaskId,
          prompt: prompt ?? null,
          model: model ?? null,
        }
      )
    },
    dispatchFailed(
      execution: Pick<LocalLoopItemExecution, 'id' | 'cloud_project_id'>,
      error: string
    ) {
      return client.post<LocalLoopItemExecution | null>(
        `/v1/cloud-projects/${execution.cloud_project_id}/executions/${execution.id}/dispatch-failed`,
        { error }
      )
    },
    list(projectId: string) {
      return client.get<ProjectAutomationRule[]>(`/v1/cloud-projects/${projectId}/automations`)
    },
    async listDingTalkChannels() {
      const channels = await client.get<AutomationDingTalkChannelResponse[]>(
        '/users/me/available-channels'
      )
      return channels.map(channel => ({
        id: channel.id,
        name: channel.name,
        channelType: channel.channel_type,
        isBound: channel.is_bound,
      }))
    },
    getDingTalkBinding(projectId: string, automationId: string) {
      return client.get<ProjectAutomationDingTalkBinding>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/dingtalk-binding`
      )
    },
    beginDingTalkBinding(projectId: string, automationId: string, version: number) {
      return client.post<ProjectAutomationDingTalkBinding>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/dingtalk-binding/pair`,
        { version }
      )
    },
    cancelDingTalkBinding(projectId: string, automationId: string) {
      return client.delete<ProjectAutomationDingTalkBinding>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/dingtalk-binding/pair`
      )
    },
    removeDingTalkBinding(projectId: string, automationId: string) {
      return client.delete<ProjectAutomationDingTalkBinding>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/dingtalk-binding`
      )
    },
    create(projectId: string, input: ProjectAutomationInput) {
      return client.post<ProjectAutomationRule>(
        `/v1/cloud-projects/${projectId}/automations`,
        input
      )
    },
    migrateWorkflow(
      projectId: string,
      input: {
        projectVersion: number
        automation: ProjectAutomationInput
        workflowDefinition: ProjectWorkflowDefinition
      }
    ) {
      return client.post<ProjectAutomationWorkflowMigrationResult>(
        `/v1/cloud-projects/${projectId}/automations/migrate-workflow`,
        input
      )
    },
    update(
      projectId: string,
      automationId: string,
      input: Partial<ProjectAutomationInput> & Pick<ProjectAutomationRule, 'version'>
    ) {
      return client.patch<ProjectAutomationRule>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}`,
        input
      )
    },
    delete(projectId: string, automationId: string) {
      return client.delete<ProjectAutomationDeleteResult>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}`
      )
    },
    rotateWebhookSecret(projectId: string, automationId: string) {
      return client.post<ProjectAutomationRule>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/rotate-webhook-secret`,
        {}
      )
    },
    runNow(projectId: string, automationId: string) {
      return client.post<ProjectAutomationRun>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/run`,
        {}
      )
    },
    runWorkflowNode(
      projectId: string,
      itemId: string,
      workflowNodeId: string,
      automationId: string
    ) {
      const query = new URLSearchParams({ automation_id: automationId })
      return client.post<ProjectAutomationRun>(
        `/v1/cloud-projects/${projectId}/loop-items/${encodeURIComponent(itemId)}/workflow-nodes/${encodeURIComponent(workflowNodeId)}/run?${query.toString()}`,
        {}
      )
    },
    listRuns(projectId: string, automationId: string) {
      return client.get<ProjectAutomationRun[]>(
        `/v1/cloud-projects/${projectId}/automations/${automationId}/runs`
      )
    },
    cancelRun(projectId: string, runId: string) {
      return client.post<ProjectAutomationRun>(
        `/v1/cloud-projects/${projectId}/automation-runs/${runId}/cancel`,
        {}
      )
    },
    retryRun(projectId: string, runId: string) {
      return client.post<ProjectAutomationRun>(
        `/v1/cloud-projects/${projectId}/automation-runs/${runId}/retry`,
        {}
      )
    },
  }
}
