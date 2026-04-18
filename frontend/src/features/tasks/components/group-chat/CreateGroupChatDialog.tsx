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
import {
  DEFAULT_GROUP_CHAT_HISTORY_WINDOW,
  updateGroupChatSettings,
} from '@/apis/group-chat'
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

export function CreateGroupChatDialog({ open, onOpenChange }: CreateGroupChatDialogProps) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const router = useRouter()
  const [title, setTitle] = useState('')
  const [selectedTeamIds, setSelectedTeamIds] = useState<number[]>([])
  const [isCreating, setIsCreating] = useState(false)
  const [selectedModel, setSelectedModel] = useState<Model | null>(null)
  const [forceOverride, setForceOverride] = useState(false)
  const [maxDays, setMaxDays] = useState(DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxDays)
  const [maxMessages, setMaxMessages] = useState(DEFAULT_GROUP_CHAT_HISTORY_WINDOW.maxMessages)

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
    return title.trim().length > 0 && selectedTeams.length > 0 && selectedModel !== null
  }, [selectedModel, selectedTeams.length, title])

  const resetForm = () => {
    setTitle('')
    setSelectedTeamIds([])
    setSelectedModel(null)
    setForceOverride(false)
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

    const groupChatPayload = buildGroupChatCreatePayload(selectedTeams, {
      maxDays,
      maxMessages,
    })

    setIsCreating(true)

    try {
      void sendMessage(
        {
          message: t('groupChat.create.initialMessage'),
          team_id: primarySelectedTeam.id,
          task_id: undefined,
          title,
          model_id:
            selectedModel?.name === '__default__' ? undefined : selectedModel?.name || undefined,
          force_override_bot_model: forceOverride,
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
                  description: error instanceof Error ? error.message : t('groupChat.create.failedDesc'),
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
      <DialogContent>
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
                <p className="text-sm text-text-secondary">{t('actions.loading')}</p>
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
              <Label htmlFor="group-chat-history-days">{t('groupChat.create.historyDaysLabel')}</Label>
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
                onChange={event =>
                  setMaxMessages(Math.max(1, Number(event.target.value) || 1))
                }
              />
            </div>
          </div>

          {primarySelectedTeam && (
            <div className="space-y-2">
              <Label>{t('models.label')}</Label>
              <ModelSelector
                selectedModel={selectedModel}
                setSelectedModel={setSelectedModel}
                forceOverride={forceOverride}
                setForceOverride={setForceOverride}
                selectedTeam={primarySelectedTeam}
                disabled={isCreating}
                isLoading={false}
              />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isCreating}>
            {t('actions.cancel')}
          </Button>
          <Button
            data-testid="group-chat-create-button"
            onClick={handleCreate}
            disabled={isCreating || !isFormValid}
          >
            {isCreating ? t('actions.creating') : t('actions.create')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
