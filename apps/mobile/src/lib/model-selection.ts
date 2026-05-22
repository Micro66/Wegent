import type { AllowedModelRef, Team, UnifiedModel } from '@/types/api'

type CompatibleProvider = 'openai' | 'claude'

export function getCompatibleProviderFromAgentType(
  agentType?: string | null,
): CompatibleProvider | null {
  if (!agentType) return null

  const normalized = agentType.toLowerCase()
  if (normalized === 'agno') return 'openai'
  if (normalized === 'claude' || normalized === 'claudecode') return 'claude'
  return null
}

export function getAllowedModelsFromTeam(team?: Team | null): AllowedModelRef[] {
  const rawAllowedModels = team?.bots?.[0]?.bot?.agent_config?.allowed_models
  if (!Array.isArray(rawAllowedModels)) return []

  return rawAllowedModels.filter((model): model is AllowedModelRef => {
    return (
      typeof model === 'object' &&
      model !== null &&
      'name' in model &&
      typeof model.name === 'string'
    )
  })
}

export function getFilteredModelsForTeam(
  models: UnifiedModel[],
  team?: Team | null,
): UnifiedModel[] {
  const compatibleProvider = getCompatibleProviderFromAgentType(team?.agent_type)
  const allowedModels = getAllowedModelsFromTeam(team)
  const allowedNames = new Set(allowedModels.map(model => model.name))

  return models
    .filter(model => {
      if (compatibleProvider && model.provider !== compatibleProvider) return false
      if (model.isAdvanced) return false
      if (allowedNames.size > 0 && !allowedNames.has(model.name)) return false
      return true
    })
    .slice()
    .sort((a, b) => {
      const displayA = (a.displayName ?? a.name).toLowerCase()
      const displayB = (b.displayName ?? b.name).toLowerCase()
      return displayA.localeCompare(displayB)
    })
}
