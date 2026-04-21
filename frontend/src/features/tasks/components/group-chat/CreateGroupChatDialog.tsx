// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { buildGroupChatCreatePayload } from '@/apis/chat'
import { DEFAULT_GROUP_CHAT_HISTORY_WINDOW, updateGroupChatSettings } from '@/apis/group-chat'
import { useTranslation } from '@/hooks/useTranslation'
import { useToast } from '@/hooks/use-toast'
import { Team, Task } from '@/types/api'
import { useTeamContext } from '@/contexts/TeamContext'
import { useChatStreamContext } from '@/features/tasks/contexts/chatStreamContext'
import { useTaskContext } from '@/features/tasks/contexts/taskContext'
import { ModelSelector, type Model } from '@/features/tasks/components/selector'
import { useUser } from '@/features/common/UserContext'

interface CreateGroupChatDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface TeamModelConfig {
  model: Model | null
  forceOverride: boolean
}

export function CreateGroupChatDialog({ open, onOpenChange }: CreateGroupChatDialogProps) {
  const { t } = useTranslation('chat')
  const { toast } = useToast()
  const router = useRouter()
  const [title, setTitle] = useState('')
  const [selectedTeamIds, setSelectedTeamIds] = useState<number[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [teamModels, setTeamModels] = useState<Record<number, TeamModelConfig>>({})
  const [maxDays, setMaxDays] = useState<number>(DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxDays)
  const [maxMessages, setMaxMessages] = useState<number>(
    DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxMessages
  )

  const { teams, isTeamsLoading } = useTeamContext()
  const { sendMessage } = useChatStreamContext()
  const { refreshTasks, setSelectedTask } = useTaskContext()
  const { user } = useUser()

  const chatTeams = useMemo(() => {
    return teams.filter(team => team.agent_type === 'chat')
  }, [teams])

  const selectedTeams = useMemo(() => {
    return chatTeams.filter(team => selectedTeamIds.includes(team.id))
  }, [chatTeams, selectedTeamIds])

  const primarySelectedTeam = selectedTeams[0] || null

  const isFormValid = useMemo(() => {
    if (title.trim().length === 0 || selectedTeams.length === 0) return false
    // Check that all selected teams have a model configured
    return selectedTeams.every(team => {
      const teamConfig = teamModels[team.id]
      return teamConfig?.model != null
    })
  }, [teamModels, selectedTeams, title])

  const resetForm = () => {
    setTitle('')
    setSelectedTeamIds([])
    setTeamModels({})
    setMaxDays(DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxDays)
    setMaxMessages(DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxMessages)
    setIsCreating(false)
  }

  const toggleTeamSelection = (teamId: number) => {
    setSelectedTeamIds(currentIds =>
      currentIds.includes(teamId)
        ? currentIds.filter(currentId => currentId !== teamId)
        : [...currentIds, teamId]
    )
  }

  const setTeamModel = (teamId: number, model: Model | null) => {
    setTeamModels(prev => ({
      ...prev,
      [teamId]: { ...prev[teamId], model },
    }))
  }

  const setTeamForceOverride = (teamId: number, forceOverride: boolean) => {
    setTeamModels(prev => ({
      ...prev,
      [teamId]: { ...prev[teamId], forceOverride },
    }))
  }

  const handleCreate = async () => {
    if (!title.trim()) {
      toast({
        title: t('groupChat.create.titleRequired'),
        variant: 'destructive',
      })
      return
    }

    if (selectedTeams.length === 0) {
      toast({
        title: t('groupChat.create.teamRequired'),
        variant: 'destructive',
      })
      return
    }

    if (!primarySelectedTeam) {
      toast({
        title: t('groupChat.create.teamRequired'),
        variant: 'destructive',
      })
      return
    }

    // Build team refs with model configurations
    const teamRefsWithModels = selectedTeams.map(team => {
      const config = teamModels[team.id]
      return {
        id: team.id,
        team_id: team.id,
        name: team.name,
        namespace: team.namespace || 'default',
        user_id: team.user_id,
        model_id: config?.model?.name === '__default__' ? undefined : config?.model?.name,
        force_override_bot_model: config?.forceOverride || false,
      }
    })

    const groupChatPayload = buildGroupChatCreatePayload(
      selectedTeams,
      {
        maxDays,
        maxMessages,
      },
      teamRefsWithModels
    )
    console.log('[CreateGroupChatDialog] teamRefsWithModels:', teamRefsWithModels)
    console.log('[CreateGroupChatDialog] groupChatPayload:', groupChatPayload)

    // Get primary team model config for initial message
    const primaryConfig = teamModels[primarySelectedTeam.id]

    setIsCreating(true)

    try {
      void sendMessage(
        {
          message: t('groupChat.create.initialMessage'),
          team_id: primarySelectedTeam.id,
          task_id: undefined,
          title,
          model_id:
            primaryConfig?.model?.name === '__default__' ? undefined : primaryConfig?.model?.name,
          force_override_bot_model: primaryConfig?.forceOverride || false,
          is_group_chat: true,
          ...groupChatPayload,
        } as Parameters<typeof sendMessage>[0],
        {
          pendingUserMessage: undefined,
          pendingAttachment: null,
          immediateTaskId: -Date.now(),
          currentUserId: user?.id,
          currentUserName: user?.user_name,
          onMessageSent: (_localMessageId: string, realTaskId: number) => {
            console.log('[CreateGroupChatDialog] groupChatPayload:', groupChatPayload)
            void updateGroupChatSettings(realTaskId, groupChatPayload)
              .then(() => {
                onOpenChange(false)
                resetForm()
                refreshTasks()
                setSelectedTask({
                  id: realTaskId,
                  title,
                  team_id: primarySelectedTeam.id,
                  is_group_chat: true,
                  teamRefs: groupChatPayload.teamRefs,
                  groupChatConfig: groupChatPayload.groupChatConfig,
                } as Task)
                router.push(`/chat?taskId=${realTaskId}`)
                toast({
                  title: t('groupChat.create.success'),
                  description: t('groupChat.create.successDesc'),
                })
              })
              .catch(error => {
                toast({
                  title: t('groupChat.create.failed'),
                  description:
                    error instanceof Error ? error.message : t('groupChat.create.failedDesc'),
                  variant: 'destructive',
                })
                setIsCreating(false)
              })
          },
          onError: error => {
            toast({
              title: t('groupChat.create.failed'),
              description: error.message || t('groupChat.create.failedDesc'),
              variant: 'destructive',
            })
            setIsCreating(false)
          },
        }
      )
    } catch (error) {
      console.error('[CreateGroupChatDialog] Failed to create group chat:', error)
      toast({
        title: t('groupChat.create.failed'),
        description: error instanceof Error ? error.message : t('groupChat.create.failedDesc'),
        variant: 'destructive',
      })
      setIsCreating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('groupChat.create.title')}</DialogTitle>
          <DialogDescription>{t('groupChat.create.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="title">{t('groupChat.create.titleLabel')}</Label>
            <Input
              id="title"
              data-testid="group-chat-title-input"
              placeholder={t('groupChat.create.titlePlaceholder')}
              value={title}
              onChange={e => setTitle(e.target.value)}
              maxLength={100}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('groupChat.create.agentsLabel')}</Label>
            <div className="space-y-2">
              {isTeamsLoading ? (
                <p className="text-sm text-text-secondary">{t('common:actions.loading')}</p>
              ) : chatTeams.length === 0 ? (
                <p className="text-sm text-text-secondary">{t('groupChat.create.noChatTeams')}</p>
              ) : (
                chatTeams.map((team: Team) => {
                  const isChecked = selectedTeamIds.includes(team.id)
                  return (
                    <label
                      key={team.id}
                      className="flex items-center gap-3 rounded-lg border border-border px-3 py-2 text-sm text-text-primary"
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleTeamSelection(team.id)}
                        data-testid={`group-chat-agent-checkbox-${team.id}`}
                      />
                      <span>{team.name}</span>
                    </label>
                  )
                })
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="group-chat-history-days">
                {t('groupChat.create.historyDaysLabel')}
              </Label>
              <Input
                id="group-chat-history-days"
                data-testid="group-chat-history-days-input"
                type="number"
                min={1}
                value={String(maxDays)}
                onChange={event => setMaxDays(Math.max(1, Number(event.target.value) || 1))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-chat-history-messages">
                {t('groupChat.create.historyMessagesLabel')}
              </Label>
              <Input
                id="group-chat-history-messages"
                data-testid="group-chat-history-messages-input"
                type="number"
                min={1}
                value={String(maxMessages)}
                onChange={event => setMaxMessages(Math.max(1, Number(event.target.value) || 1))}
              />
            </div>
          </div>

          {/* Per-team model selectors */}
          {selectedTeams.length > 0 && (
            <div className="space-y-4 border-t border-border pt-4">
              <Label className="font-medium">
                {t('groupChat.create.modelsLabel') || '智能体模型配置'}
              </Label>
              {selectedTeams.map(team => {
                const config = teamModels[team.id] || { model: null, forceOverride: false }
                return (
                  <div key={team.id} className="space-y-2 border border-border rounded-lg p-3">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <span className="text-text-primary">{team.name}</span>
                    </div>
                    <ModelSelector
                      selectedModel={config.model}
                      setSelectedModel={model => setTeamModel(team.id, model)}
                      forceOverride={config.forceOverride}
                      setForceOverride={force => setTeamForceOverride(team.id, force)}
                      selectedTeam={team}
                      disabled={isCreating}
                      isLoading={false}
                    />
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isCreating}>
            {t('common:actions.cancel')}
          </Button>
          <Button
            data-testid="group-chat-create-button"
            onClick={handleCreate}
            disabled={isCreating || !isFormValid}
          >
            {isCreating ? t('common:actions.creating') : t('common:actions.create')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
