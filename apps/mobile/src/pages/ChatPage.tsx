import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChatHeader } from '@/components/ChatHeader'
import { MessageList } from '@/components/MessageList'
import { ChatInput } from '@/components/ChatInput'
import { AgentSheet } from '@/components/AgentSheet'
import { ModelPage } from '@/components/ModelPage'
import { useChat } from '@/hooks/useChat'
import { useModels } from '@/hooks/useModels'
import { useTeams } from '@/hooks/useTeams'
import { apiFetch } from '@/lib/api-client'
import { getFilteredModelsForTeam } from '@/lib/model-selection'
import type { TaskDetail, Team, UnifiedModel } from '@/types/api'

const getModelNameFromTeam = (team?: Team | null) => {
  const bots = team?.bots ?? []
  for (const botInfo of bots) {
    const bindModel = botInfo.bot?.agent_config?.bind_model
    if (typeof bindModel === 'string' && bindModel.trim()) {
      return bindModel
    }
  }
  return undefined
}

const getModelDisplayName = (models: UnifiedModel[], modelName?: string | null) => {
  if (!modelName) return undefined
  const model = models.find(
    (item) => item.name === modelName || item.displayName === modelName,
  )
  return model?.displayName ?? model?.name ?? modelName
}

export function ChatPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const {
    messages,
    isStreaming,
    activeTaskId,
    sendMessage,
    stopStream,
    clearMessages,
    loadMessages,
  } = useChat()
  const { teams } = useTeams()
  const { models } = useModels()
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null)
  const [selectedModel, setSelectedModel] = useState<string>()
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [agentSheetOpen, setAgentSheetOpen] = useState(false)
  const [modelPageOpen, setModelPageOpen] = useState(false)

  const taskTeamId = taskDetail?.team?.id ?? taskDetail?.team_id
  const currentTeam =
    teams.find((t) => t.id === (selectedTeamId ?? taskTeamId)) ??
    taskDetail?.team ??
    teams[0]
  const currentModelRawName =
    selectedModel ?? taskDetail?.model_id ?? getModelNameFromTeam(currentTeam)
  const modelDisplayName = getModelDisplayName(models, currentModelRawName)
  const isModelOverride = Boolean(selectedModel ?? taskDetail?.model_id)
  const currentModelName =
    modelDisplayName && isModelOverride ? `${modelDisplayName}(覆盖)` : modelDisplayName
  const selectableModels = useMemo(() => {
    return getFilteredModelsForTeam(models, currentTeam)
  }, [models, currentTeam])
  const hasMessages = messages.length > 0

  // Load messages when navigating to a historical task
  const taskIdFromUrl = searchParams.get('task')
  useEffect(() => {
    if (taskIdFromUrl) {
      loadMessages(Number(taskIdFromUrl))
      apiFetch<TaskDetail>(`/tasks/${taskIdFromUrl}`)
        .then((detail) => {
          setTaskDetail(detail)
          setSelectedTeamId(detail.team?.id ?? detail.team_id ?? null)
          setSelectedModel(undefined)
        })
        .catch(console.error)
    } else {
      Promise.resolve().then(() => setTaskDetail(null))
    }
  }, [taskIdFromUrl, loadMessages])

  useEffect(() => {
    if (!taskIdFromUrl && activeTaskId) {
      navigate(`/?task=${activeTaskId}`, { replace: true })
    }
  }, [activeTaskId, navigate, taskIdFromUrl])

  const handleSend = (text: string) => {
    if (!currentTeam) return
    sendMessage(currentTeam.id, text, taskIdFromUrl ? Number(taskIdFromUrl) : undefined)
  }

  const handleSelectAgent = (teamId: number) => {
    setSelectedTeamId(teamId)
    setAgentSheetOpen(false)
    clearMessages()
  }

  const handleSelectModel = (model: UnifiedModel) => {
    setSelectedModel(model.name)
    setModelPageOpen(false)
  }

  const handleHeaderSelectorClick = () => {
    if (taskIdFromUrl) {
      setModelPageOpen(true)
      return
    }

    setAgentSheetOpen(true)
  }

  return (
    <div className="flex h-dvh flex-col bg-white">
      <ChatHeader
        agentName={currentTeam?.name ?? 'ChatGPT'}
        modelName={currentModelName}
        onMenuClick={() => navigate('/sidebar')}
        onAgentClick={handleHeaderSelectorClick}
      />

      {hasMessages ? (
        <MessageList messages={messages} />
      ) : (
        <div className="flex-1" />
      )}

      <ChatInput
        placeholder={`询问 ${currentTeam?.name ?? 'ChatGPT'}`}
        isStreaming={isStreaming}
        onSend={handleSend}
        onStop={stopStream}
      />

      <AgentSheet
        open={agentSheetOpen}
        onClose={() => setAgentSheetOpen(false)}
        teams={teams}
        selectedTeamId={currentTeam?.id}
        onSelectAgent={handleSelectAgent}
      />

      {modelPageOpen && (
        <ModelPage
          onBack={() => setModelPageOpen(false)}
          models={selectableModels}
          selectedModel={currentModelRawName}
          onSelectModel={handleSelectModel}
        />
      )}
    </div>
  )
}
