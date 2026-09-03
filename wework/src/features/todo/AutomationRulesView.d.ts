import type { ComponentType } from 'react'
import type {
  AutomationExecutionCatalog,
  AutomationUiRule,
  AutomationUiRun,
} from './automationRuleBackend'
import type {
  AutomationDingTalkChannel,
  ProjectAutomationDingTalkBinding,
} from '@/api/projectAutomations'

export interface AutomationRulesViewProps {
  rules: AutomationUiRule[]
  runs: AutomationUiRun[]
  loading?: boolean
  error?: string
  canManage?: boolean
  projectTags?: string[]
  executionCatalog?: AutomationExecutionCatalog
  onReload?: () => Promise<void>
  onLoadExecutionCatalog?: () => Promise<AutomationExecutionCatalog>
  onLoadExecutionPlugins?: () => Promise<AutomationExecutionCatalog['plugins']>
  onLoadRuns?: () => Promise<AutomationUiRun[]>
  onSaveRule?: (rule: AutomationUiRule) => Promise<AutomationUiRule>
  onToggleRule?: (rule: AutomationUiRule, enabled: boolean) => Promise<AutomationUiRule>
  onDuplicateRule?: (rule: AutomationUiRule) => Promise<AutomationUiRule>
  onDeleteRule?: (rule: AutomationUiRule) => Promise<void>
  dingtalkChannels?: AutomationDingTalkChannel[]
  onBeginDingTalkBinding?: (rule: AutomationUiRule) => Promise<ProjectAutomationDingTalkBinding>
  onCancelDingTalkBinding?: (rule: AutomationUiRule) => Promise<ProjectAutomationDingTalkBinding>
  onRemoveDingTalkBinding?: (rule: AutomationUiRule) => Promise<ProjectAutomationDingTalkBinding>
}

export const AutomationRulesView: ComponentType<AutomationRulesViewProps>
