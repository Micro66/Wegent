// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from '@/hooks/useTranslation'
import { useToast } from '@/hooks/use-toast'
import { userApis } from '@/apis/user'
import { teamApis } from '@/apis/team'
import { useSocket } from '@/contexts/SocketContext'
import { ServerEvents, type IMGroupDiscoveredPayload } from '@/types/socket'
import type { IMChannelUserBinding, Team } from '@/types/api'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import {
  TrashIcon,
  PlusIcon,
  UserIcon,
  UsersIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline'
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/solid'

// Binding step type
type BindingStep = 'initial' | 'waiting' | 'select_team' | 'success'

// Discovered group info from WebSocket
interface DiscoveredGroup {
  conversation_id: string
  group_name: string
}

export default function IMChannelBindings() {
  const { t } = useTranslation('settings')
  const { toast } = useToast()
  const { socket } = useSocket()

  // Data states
  const [bindings, setBindings] = useState<IMChannelUserBinding[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingTeams, setIsLoadingTeams] = useState(false)

  // Dialog states
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [currentChannelId, setCurrentChannelId] = useState<number | null>(null)
  const [bindingStep, setBindingStep] = useState<BindingStep>('initial')
  const [discoveredGroup, setDiscoveredGroup] = useState<DiscoveredGroup | null>(null)
  const [selectedTeamId, setSelectedTeamId] = useState<string>('')
  const [isProcessing, setIsProcessing] = useState(false)

  // Fetch bindings and teams on mount
  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setIsLoading(true)
    setIsLoadingTeams(true)
    try {
      const [bindingsData, teamsData] = await Promise.all([
        userApis.getMyIMBindings(),
        teamApis.getTeams({ page: 1, limit: 100 }, 'personal'),
      ])
      setBindings(bindingsData)
      setTeams(teamsData.items)
    } catch (error) {
      console.error('Failed to fetch IM bindings:', error)
      toast({
        variant: 'destructive',
        title: t('im_bindings.load_failed'),
      })
    } finally {
      setIsLoading(false)
      setIsLoadingTeams(false)
    }
  }

  // Handle private team selection change
  const handlePrivateTeamChange = async (channelId: number, teamId: string) => {
    try {
      const teamIdNum = teamId === 'default' ? undefined : parseInt(teamId, 10)
      await userApis.updateIMBinding(channelId, { private_team_id: teamIdNum })
      // Update local state
      setBindings(prev =>
        prev.map(binding =>
          binding.channel_id === channelId ? { ...binding, private_team_id: teamIdNum } : binding
        )
      )
      toast({
        title: t('im_bindings.private_team_updated'),
      })
    } catch (error) {
      console.error('Failed to update private team:', error)
      toast({
        variant: 'destructive',
        title: t('im_bindings.update_failed'),
      })
    }
  }

  // Handle remove group binding
  const handleRemoveGroupBinding = async (channelId: number, conversationId: string) => {
    try {
      await userApis.removeGroupBinding(channelId, conversationId)
      // Update local state
      setBindings(prev =>
        prev.map(binding =>
          binding.channel_id === channelId
            ? {
                ...binding,
                group_bindings: binding.group_bindings.filter(
                  g => g.conversation_id !== conversationId
                ),
              }
            : binding
        )
      )
      toast({
        title: t('im_bindings.group_removed'),
      })
    } catch (error) {
      console.error('Failed to remove group binding:', error)
      toast({
        variant: 'destructive',
        title: t('im_bindings.remove_failed'),
      })
    }
  }

  // Start binding flow
  const handleStartBinding = async (channelId: number) => {
    setCurrentChannelId(channelId)
    setBindingStep('initial')
    setDiscoveredGroup(null)
    setSelectedTeamId('')
    setIsDialogOpen(true)
  }

  // Listen for IM group discovered event via Socket.IO
  useEffect(() => {
    // Always set up listener when dialog is open, regardless of binding step
    // This ensures we don't miss events due to race conditions
    if (!socket || !isDialogOpen || currentChannelId === null) {
      return
    }

    const handleGroupDiscovered = (payload: IMGroupDiscoveredPayload) => {
      // Accept the event if channel_id matches, regardless of current binding step
      // This handles race conditions where event arrives before state updates
      if (payload.channel_id === currentChannelId) {
        setDiscoveredGroup({
          conversation_id: payload.conversation_id,
          group_name: payload.group_name,
        })
        setBindingStep('select_team')
      }
    }

    socket.on(ServerEvents.IM_GROUP_DISCOVERED, handleGroupDiscovered)

    return () => {
      socket.off(ServerEvents.IM_GROUP_DISCOVERED, handleGroupDiscovered)
    }
  }, [socket, isDialogOpen, bindingStep, currentChannelId])

  // Start waiting for group message
  const startWaitingForGroup = async () => {
    if (currentChannelId === null) {
      return
    }

    setIsProcessing(true)
    try {
      await userApis.startIMBindingSession(currentChannelId)
      setBindingStep('waiting')
    } catch (error) {
      console.error('[IMBinding] Failed to start binding session:', error)
      toast({
        variant: 'destructive',
        title: t('im_bindings.start_session_failed'),
      })
    } finally {
      setIsProcessing(false)
    }
  }

  // Cancel binding session
  const handleCancelBinding = async () => {
    if (currentChannelId !== null) {
      try {
        await userApis.cancelIMBindingSession(currentChannelId)
      } catch (error) {
        console.error('Failed to cancel binding session:', error)
      }
    }

    setIsDialogOpen(false)
    setBindingStep('initial')
    setDiscoveredGroup(null)
    setSelectedTeamId('')
    setCurrentChannelId(null)
  }

  // Confirm group binding
  const handleConfirmBinding = async () => {
    if (currentChannelId === null || discoveredGroup === null || !selectedTeamId) return

    setIsProcessing(true)
    try {
      await userApis.updateIMBinding(currentChannelId, {
        group: {
          conversation_id: discoveredGroup.conversation_id,
          group_name: discoveredGroup.group_name,
          team_id: parseInt(selectedTeamId, 10),
        },
      })

      setBindingStep('success')

      // Refresh bindings data
      const updatedBindings = await userApis.getMyIMBindings()
      setBindings(updatedBindings)

      // Auto-close after 2 seconds
      setTimeout(() => {
        setIsDialogOpen(false)
        setBindingStep('initial')
        setDiscoveredGroup(null)
        setSelectedTeamId('')
        setCurrentChannelId(null)
      }, 2000)
    } catch (error) {
      console.error('Failed to confirm binding:', error)
      toast({
        variant: 'destructive',
        title: t('im_bindings.binding_failed'),
      })
    } finally {
      setIsProcessing(false)
    }
  }

  // Get team name by ID
  const getTeamName = (teamId?: number) => {
    if (!teamId) return t('im_bindings.default_team')
    const team = teams.find(t => t.id === teamId)
    return team?.name || t('im_bindings.unknown_team')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Spinner className="h-8 w-8" />
      </div>
    )
  }

  if (bindings.length === 0) {
    return (
      <div className="rounded-md border border-border bg-base p-4">
        <div className="space-y-1">
          <h3 className="text-base font-medium text-text-primary">{t('im_bindings.title')}</h3>
          <p className="text-sm text-text-muted">{t('im_bindings.description')}</p>
        </div>
        <div className="mt-4 rounded-md border border-border/70 bg-surface px-3 py-4 text-center">
          <p className="text-sm text-text-muted">{t('im_bindings.no_channels')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-base p-4">
      <div className="space-y-1">
        <h3 className="text-base font-medium text-text-primary">{t('im_bindings.title')}</h3>
        <p className="text-sm text-text-muted">{t('im_bindings.description')}</p>
      </div>

      <Accordion type="multiple" className="space-y-2">
        {bindings.map(binding => (
          <AccordionItem
            key={binding.channel_id}
            value={String(binding.channel_id)}
            className="rounded-md border border-border/70 bg-surface"
          >
            <AccordionTrigger className="px-4 py-3 hover:no-underline">
              <div className="flex items-center gap-3">
                <ChatBubbleLeftRightIcon className="h-5 w-5 text-text-primary flex-shrink-0" />
                <span className="text-sm font-medium text-text-primary">
                  {binding.channel_name}
                </span>
                <span className="text-xs text-text-muted">({binding.channel_type})</span>
              </div>
            </AccordionTrigger>
            <AccordionContent className="px-4 pb-4">
              <div className="space-y-4">
                {/* Private Agent Section */}
                <Card className="border-border/50">
                  <CardHeader className="py-3">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <UserIcon className="h-4 w-4" />
                      {t('im_bindings.private_agent')}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="py-0">
                    <Select
                      value={binding.private_team_id ? String(binding.private_team_id) : 'default'}
                      onValueChange={value => handlePrivateTeamChange(binding.channel_id, value)}
                      disabled={isLoadingTeams}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('im_bindings.select_team')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="default">
                          {t('im_bindings.use_channel_default')}
                        </SelectItem>
                        {teams.map(team => (
                          <SelectItem key={team.id} value={String(team.id)}>
                            {team.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </CardContent>
                </Card>

                {/* Group Bindings Section */}
                <Card className="border-border/50">
                  <CardHeader className="py-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <UsersIcon className="h-4 w-4" />
                        {t('im_bindings.bound_groups')}
                      </CardTitle>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => handleStartBinding(binding.channel_id)}
                        data-testid={`add-group-binding-${binding.channel_id}`}
                      >
                        <PlusIcon className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="py-0 space-y-2">
                    {binding.group_bindings.length === 0 ? (
                      <p className="text-sm text-text-muted py-2">
                        {t('im_bindings.no_group_bindings')}
                      </p>
                    ) : (
                      binding.group_bindings.map(group => (
                        <div
                          key={group.conversation_id}
                          className="flex items-center justify-between rounded-md border border-border/50 bg-base px-3 py-2"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium text-text-primary truncate">
                              {group.group_name}
                            </p>
                            <p className="text-xs text-text-muted">
                              {t('im_bindings.using_team', { team: getTeamName(group.team_id) })}
                            </p>
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 flex-shrink-0 hover:text-error"
                            onClick={() =>
                              handleRemoveGroupBinding(binding.channel_id, group.conversation_id)
                            }
                            data-testid={`remove-group-binding-${group.conversation_id}`}
                          >
                            <TrashIcon className="h-4 w-4" />
                          </Button>
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>

      {/* Binding Dialog */}
      <Dialog
        open={isDialogOpen}
        onOpenChange={open => {
          if (!open) {
            handleCancelBinding()
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('im_bindings.bind_dialog.title')}</DialogTitle>
            <DialogDescription>{t('im_bindings.bind_dialog.description')}</DialogDescription>
          </DialogHeader>

          <div className="py-6">
            {/* Step 1: Initial */}
            {bindingStep === 'initial' && (
              <div className="space-y-4 text-center">
                <div className="flex justify-center">
                  <div className="rounded-full bg-primary/10 p-4">
                    <ChatBubbleLeftRightIcon className="h-8 w-8 text-primary" />
                  </div>
                </div>
                <p className="text-sm text-text-muted">
                  {t('im_bindings.bind_dialog.initial_instruction')}
                </p>
                <Button
                  onClick={startWaitingForGroup}
                  disabled={isProcessing}
                  className="w-full"
                  variant="primary"
                  data-testid="start-bind-button"
                >
                  {isProcessing ? (
                    <>
                      <Spinner className="mr-2 h-4 w-4" />
                      {t('im_bindings.bind_dialog.starting')}
                    </>
                  ) : (
                    t('im_bindings.bind_dialog.start_button')
                  )}
                </Button>
              </div>
            )}

            {/* Step 2: Waiting */}
            {bindingStep === 'waiting' && (
              <div className="space-y-4 text-center">
                <div className="flex justify-center">
                  <Spinner className="h-8 w-8" />
                </div>
                <p className="text-sm text-text-muted">
                  {t('im_bindings.bind_dialog.waiting_message')}
                </p>
                <Button
                  onClick={handleCancelBinding}
                  variant="outline"
                  className="w-full"
                  data-testid="cancel-waiting-button"
                >
                  {t('im_bindings.bind_dialog.cancel_button')}
                </Button>
              </div>
            )}

            {/* Step 3: Select Team */}
            {bindingStep === 'select_team' && discoveredGroup && (
              <div className="space-y-4">
                <div className="rounded-md bg-primary/5 p-3">
                  <p className="text-sm font-medium text-text-primary">
                    {t('im_bindings.bind_dialog.discovered_group')}
                  </p>
                  <p className="text-sm text-text-muted">{discoveredGroup.group_name}</p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-text-primary">
                    {t('im_bindings.bind_dialog.select_team_label')}
                  </label>
                  <Select value={selectedTeamId} onValueChange={setSelectedTeamId}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={t('im_bindings.select_team')} />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.map(team => (
                        <SelectItem key={team.id} value={String(team.id)}>
                          {team.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {/* Step 4: Success */}
            {bindingStep === 'success' && (
              <div className="space-y-4 text-center">
                <div className="flex justify-center">
                  <CheckCircleIcon className="h-12 w-12 text-success" />
                </div>
                <p className="text-lg font-medium text-text-primary">
                  {t('im_bindings.bind_dialog.success_title')}
                </p>
                <p className="text-sm text-text-muted">
                  {t('im_bindings.bind_dialog.success_message')}
                </p>
              </div>
            )}
          </div>

          {/* Dialog Footer - Only show for select_team step */}
          {bindingStep === 'select_team' && (
            <DialogFooter>
              <Button
                variant="outline"
                onClick={handleCancelBinding}
                disabled={isProcessing}
                data-testid="cancel-select-button"
              >
                {t('im_bindings.bind_dialog.cancel_button')}
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmBinding}
                disabled={!selectedTeamId || isProcessing}
                data-testid="confirm-binding-button"
              >
                {isProcessing ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    {t('im_bindings.bind_dialog.confirming')}
                  </>
                ) : (
                  t('im_bindings.bind_dialog.confirm_button')
                )}
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
