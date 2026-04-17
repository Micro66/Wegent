// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useCallback, useEffect, useState, useMemo } from 'react'
import '@/features/common/scrollbar.css'
import { RiRobot2Line } from 'react-icons/ri'
import LoadingState from '@/features/common/LoadingState'
import {
  PencilIcon,
  TrashIcon,
  DocumentDuplicateIcon,
  ChatBubbleLeftEllipsisIcon,
  ShareIcon,
  CodeBracketIcon,
  LinkSlashIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { Link as LinkIcon } from 'lucide-react'
import { Bot, Team, IMChannelUserBinding } from '@/types/api'
import { fetchTeamsList, deleteTeam, shareTeam, checkTeamRunningTasks } from '../services/teams'
import { CheckRunningTasksResponse } from '@/apis/common'
import { fetchBotsList } from '../services/bots'
import TeamEditDialog from './TeamEditDialog'
import BotList from './BotList'
import { ForceDeleteTaskSummary } from './ForceDeleteTaskSummary'
import UnifiedAddButton from '@/components/common/UnifiedAddButton'
import TeamShareModal from './TeamShareModal'
import TeamCreationWizard from './wizard/TeamCreationWizard'
import { useTranslation } from '@/hooks/useTranslation'
import { useToast } from '@/hooks/use-toast'
import { sortTeamsByUpdatedAt } from '@/utils/team'
import { isGroupTeam, isPublicTeam, isSharedTeam } from '@/utils/team-permissions'
import type { BaseRole } from '@/types/base-role'
import { sortBotsByUpdatedAt } from '@/utils/bot'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown'
import { ResourceListItem } from '@/components/common/ResourceListItem'
import { TeamIconDisplay } from './teams/TeamIconDisplay'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { userApis } from '@/apis/user'

interface TeamListProps {
  scope?: 'personal' | 'group' | 'all'
  groupName?: string
  groupRoleMap?: Map<string, BaseRole>
  onEditResource?: (namespace: string) => void
}

// Mode filter type
type ModeFilter = 'all' | 'chat' | 'code'

export default function TeamList({
  scope = 'personal',
  groupName,
  groupRoleMap,
  onEditResource,
}: TeamListProps) {
  const { t } = useTranslation(['common', 'wizard', 'settings'])
  const { toast } = useToast()
  const [teams, setTeams] = useState<Team[]>([])
  const [bots, setBots] = useState<Bot[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null)
  const [prefillTeam, setPrefillTeam] = useState<Team | null>(null)
  const [deleteConfirmVisible, setDeleteConfirmVisible] = useState(false)
  const [forceDeleteConfirmVisible, setForceDeleteConfirmVisible] = useState(false)
  const [teamToDelete, setTeamToDelete] = useState<number | null>(null)
  const [isUnbindingSharedTeam, setIsUnbindingSharedTeam] = useState(false)
  const [runningTasksInfo, setRunningTasksInfo] = useState<CheckRunningTasksResponse | null>(null)
  const [isCheckingTasks, setIsCheckingTasks] = useState(false)
  const [shareModalVisible, setShareModalVisible] = useState(false)
  const [shareData, setShareData] = useState<{ teamName: string; shareUrl: string } | null>(null)
  const [sharingId, setSharingId] = useState<number | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [botListVisible, setBotListVisible] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [modeFilter, setModeFilter] = useState<ModeFilter>('all')
  const [wizardOpen, setWizardOpen] = useState(false)
  const [imBindings, setImBindings] = useState<IMChannelUserBinding[]>([])
  const [isLoadingBindings, setIsLoadingBindings] = useState(false)
  const router = useRouter()

  // Switch binding confirmation dialog state
  const [switchBindingDialog, setSwitchBindingDialog] = useState<{
    open: boolean
    channelId: number
    conversationId: string
    groupName: string
    currentTeamName: string | null
    newTeamId: number
  }>({
    open: false,
    channelId: 0,
    conversationId: '',
    groupName: '',
    currentTeamName: null,
    newTeamId: 0,
  })

  const setTeamsSorted = useCallback<React.Dispatch<React.SetStateAction<Team[]>>>(
    updater => {
      setTeams(prev => {
        const next =
          typeof updater === 'function' ? (updater as (value: Team[]) => Team[])(prev) : updater
        return sortTeamsByUpdatedAt(next)
      })
    },
    [setTeams]
  )

  const setBotsSorted = useCallback<React.Dispatch<React.SetStateAction<Bot[]>>>(
    updater => {
      setBots(prev => {
        const next =
          typeof updater === 'function' ? (updater as (value: Bot[]) => Bot[])(prev) : updater
        return sortBotsByUpdatedAt(next)
      })
    },
    [setBots]
  )

  useEffect(() => {
    async function loadData() {
      setIsLoading(true)
      try {
        const [teamsData, botsData] = await Promise.all([
          fetchTeamsList(scope, groupName),
          fetchBotsList(scope, groupName),
        ])
        setTeamsSorted(teamsData)
        setBotsSorted(botsData)
      } catch {
        toast({
          variant: 'destructive',
          title: t('common:teams.loading'),
        })
      } finally {
        setIsLoading(false)
      }
    }
    loadData()
  }, [toast, setBotsSorted, setTeamsSorted, t, scope, groupName])

  // Fetch IM bindings when in personal scope
  useEffect(() => {
    if (scope === 'personal') {
      fetchIMBindings()
    }
  }, [scope])

  const fetchIMBindings = async () => {
    setIsLoadingBindings(true)
    try {
      const bindings = await userApis.getMyIMBindings()
      setImBindings(bindings)
    } catch (error) {
      console.error('Failed to fetch IM bindings:', error)
    } finally {
      setIsLoadingBindings(false)
    }
  }

  // Get bindings that use this team
  const getTeamBindings = (teamId: number) => {
    return imBindings.filter(
      binding =>
        binding.private_team_id === teamId || binding.group_bindings.some(g => g.team_id === teamId)
    )
  }

  // Get available channels for binding (not already bound to this team as private)
  const getAvailableChannelsForBinding = (teamId: number) => {
    return imBindings.filter(binding => binding.private_team_id !== teamId)
  }

  // Handle unbind from private
  const handleUnbindPrivate = async (channelId: number) => {
    try {
      await userApis.updateIMBinding(channelId, { private_team_id: null })
      // Update local state
      setImBindings(prev =>
        prev.map(binding =>
          binding.channel_id === channelId ? { ...binding, private_team_id: undefined } : binding
        )
      )
      toast({
        title: t('settings:im_bindings.private_team_updated'),
      })
    } catch (error) {
      console.error('Failed to unbind private team:', error)
      toast({
        variant: 'destructive',
        title: t('settings:im_bindings.update_failed'),
      })
    }
  }

  // Handle unbind from group
  const handleUnbindGroup = async (channelId: number, conversationId: string) => {
    try {
      await userApis.removeGroupBinding(channelId, conversationId)
      // Update local state
      setImBindings(prev =>
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
        title: t('settings:im_bindings.group_removed'),
      })
    } catch (error) {
      console.error('Failed to remove group binding:', error)
      toast({
        variant: 'destructive',
        title: t('settings:im_bindings.remove_failed'),
      })
    }
  }

  // Handle bind to private
  const handleBindToPrivate = async (channelId: number, teamId: number) => {
    try {
      await userApis.updateIMBinding(channelId, { private_team_id: teamId })
      // Update local state
      setImBindings(prev =>
        prev.map(binding =>
          binding.channel_id === channelId ? { ...binding, private_team_id: teamId } : binding
        )
      )
      toast({
        title: t('settings:im_bindings.private_team_updated'),
      })
    } catch (error) {
      console.error('Failed to bind private team:', error)
      toast({
        variant: 'destructive',
        title: t('settings:im_bindings.update_failed'),
      })
    }
  }

  // Handle bind/switch group binding
  const handleBindToGroup = async (
    channelId: number,
    conversationId: string,
    teamId: number,
    groupName: string
  ) => {
    try {
      await userApis.updateIMBinding(channelId, {
        group: {
          conversation_id: conversationId,
          group_name: groupName,
          team_id: teamId,
        },
      })
      // Refresh bindings to get updated data
      const bindings = await userApis.getMyIMBindings()
      setImBindings(bindings)
      toast({
        title: t('settings:im_bindings.group_binding_updated'),
      })
    } catch (error) {
      console.error('Failed to bind group:', error)
      toast({
        variant: 'destructive',
        title: t('settings:im_bindings.binding_failed'),
      })
    }
  }

  // Open switch binding confirmation dialog
  const openSwitchBindingDialog = (
    channelId: number,
    conversationId: string,
    groupName: string,
    currentTeamName: string | null,
    newTeamId: number
  ) => {
    setSwitchBindingDialog({
      open: true,
      channelId,
      conversationId,
      groupName,
      currentTeamName,
      newTeamId,
    })
  }

  // Confirm switch binding
  const confirmSwitchBinding = async () => {
    const { channelId, conversationId, newTeamId, groupName } = switchBindingDialog
    await handleBindToGroup(channelId, conversationId, newTeamId, groupName)
    setSwitchBindingDialog(prev => ({ ...prev, open: false }))
  }

  useEffect(() => {
    if (editingTeamId === null) {
      setPrefillTeam(null)
    }
  }, [editingTeamId])

  const handleCreateTeam = () => {
    // Validation for group scope: must have groupName
    if (scope === 'group' && !groupName) {
      toast({
        variant: 'destructive',
        title: t('common:teams.group_required_title'),
        description: t('common:teams.group_required_message'),
      })
      return
    }

    setPrefillTeam(null)
    setEditingTeamId(0) // Use 0 to mark new creation
    setEditDialogOpen(true)
  }

  const handleEditTeam = (team: Team) => {
    // Notify parent to update group selector if editing a group resource
    if (onEditResource && team.namespace && team.namespace !== 'default') {
      onEditResource(team.namespace)
    }
    setPrefillTeam(null)
    setEditingTeamId(team.id)
    setEditDialogOpen(true)
  }

  const handleCopyTeam = (team: Team) => {
    const clone: Team = {
      ...team,
      bots: team.bots.map(bot => ({ ...bot })),
      workflow: team.workflow ? { ...team.workflow } : {},
    }
    setPrefillTeam(clone)
    setEditingTeamId(0)
    setEditDialogOpen(true)
  }

  const handleCloseEditDialog = () => {
    setEditDialogOpen(false)
    setEditingTeamId(null)
    setPrefillTeam(null)
  }

  const handleWizardSuccess = async (teamId: number, teamName: string) => {
    toast({
      title: t('wizard:create_agent'),
      description: `${teamName}`,
    })
    // Reload teams list
    const teamsData = await fetchTeamsList(scope, groupName)
    setTeamsSorted(teamsData)
    setWizardOpen(false)
  }

  const handleOpenWizard = () => {
    // Validation for group scope: must have groupName
    if (scope === 'group' && !groupName) {
      toast({
        variant: 'destructive',
        title: t('common:teams.group_required_title'),
        description: t('common:teams.group_required_message'),
      })
      return
    }
    setWizardOpen(true)
  }

  // Get target page based on team's bind_mode and current filter
  const getTargetPage = (team: Team): 'chat' | 'code' | 'knowledge' | 'task' | 'video' => {
    const bindMode = team.bind_mode || ['chat', 'code']
    // If team only supports one mode, use that
    if (bindMode.length === 1) {
      return bindMode[0] as 'chat' | 'code' | 'knowledge' | 'task' | 'video'
    }
    // If team supports both, use current filter (default to 'chat' if filter is 'all')
    if (modeFilter !== 'all') {
      return modeFilter
    }
    // Default to 'chat' when filter is 'all' and team supports both
    return 'chat'
  }

  const handleChatTeam = (team: Team) => {
    const params = new URLSearchParams()
    params.set('teamId', String(team.id))
    const targetPage = getTargetPage(team)
    router.push(`/${targetPage}?${params.toString()}`)
  }

  // Filter teams based on mode filter
  const filteredTeams = useMemo(() => {
    if (modeFilter === 'all') {
      return teams
    }
    return teams.filter(team => {
      const bindMode = team.bind_mode || ['chat', 'code']
      return bindMode.includes(modeFilter)
    })
  }, [teams, modeFilter])

  // Helper function to check permissions for a specific group resource
  const canEditGroupResource = (namespace: string) => {
    if (!groupRoleMap) return false
    const role = groupRoleMap.get(namespace)
    return role === 'Owner' || role === 'Maintainer' || role === 'Developer'
  }

  const canDeleteGroupResource = (namespace: string) => {
    if (!groupRoleMap) return false
    const role = groupRoleMap.get(namespace)
    return role === 'Owner' || role === 'Maintainer'
  }

  // Check if user can create in the current group context
  // When scope is 'group', check the specific groupName; only Owner/Maintainer can create
  const canCreateInCurrentGroup = (() => {
    if (scope !== 'group' || !groupName || !groupRoleMap) return false
    const role = groupRoleMap.get(groupName)
    return role === 'Owner' || role === 'Maintainer'
  })()

  const handleDelete = async (teamId: number) => {
    setTeamToDelete(teamId)
    setIsCheckingTasks(true)

    // Check if this is a shared team
    const team = teams.find(t => t.id === teamId)
    const isShared = team?.share_status === 2
    setIsUnbindingSharedTeam(isShared)

    // For shared teams, skip running tasks check and show unbind confirmation directly
    if (isShared) {
      setIsCheckingTasks(false)
      setDeleteConfirmVisible(true)
      return
    }

    try {
      // Check if team has running tasks
      const result = await checkTeamRunningTasks(teamId)
      setRunningTasksInfo(result)

      if (result.has_running_tasks) {
        // Show force delete confirmation dialog
        setForceDeleteConfirmVisible(true)
      } else {
        // Show normal delete confirmation dialog
        setDeleteConfirmVisible(true)
      }
    } catch (e) {
      // If check fails, show normal delete dialog
      console.error('Failed to check running tasks:', e)
      setDeleteConfirmVisible(true)
    } finally {
      setIsCheckingTasks(false)
    }
  }

  const handleConfirmDelete = async () => {
    if (!teamToDelete) return

    setIsDeleting(true)
    try {
      await deleteTeam(teamToDelete)
      setTeamsSorted(prev => prev.filter(team => team.id !== teamToDelete))
      setDeleteConfirmVisible(false)
      setTeamToDelete(null)
      setRunningTasksInfo(null)
    } catch {
      toast({
        variant: 'destructive',
        title: t('common:teams.delete'),
      })
    } finally {
      setIsDeleting(false)
    }
  }

  const handleForceDelete = async () => {
    if (!teamToDelete) return

    setIsDeleting(true)
    try {
      await deleteTeam(teamToDelete, true)
      setTeamsSorted(prev => prev.filter(team => team.id !== teamToDelete))
      setForceDeleteConfirmVisible(false)
      setTeamToDelete(null)
      setRunningTasksInfo(null)
    } catch {
      toast({
        variant: 'destructive',
        title: t('common:teams.delete'),
      })
    } finally {
      setIsDeleting(false)
    }
  }

  const handleCancelDelete = () => {
    setDeleteConfirmVisible(false)
    setForceDeleteConfirmVisible(false)
    setTeamToDelete(null)
    setRunningTasksInfo(null)
    setIsUnbindingSharedTeam(false)
  }

  const handleShareTeam = async (team: Team) => {
    setSharingId(team.id)
    try {
      const response = await shareTeam(team.id)
      setShareData({
        teamName: team.name,
        shareUrl: response.share_url,
      })
      setShareModalVisible(true)
      // Update team status to sharing
      setTeamsSorted(prev => prev.map(t => (t.id === team.id ? { ...t, share_status: 1 } : t)))
    } catch {
      toast({
        variant: 'destructive',
        title: t('common:teams.share_failed'),
      })
    } finally {
      setSharingId(null)
    }
  }

  const handleCloseShareModal = () => {
    setShareModalVisible(false)
    setShareData(null)
  }

  // Check if edit button should be shown (uses shared permission utility)
  // Note: shouldShowEdit doesn't need userId because it checks structural properties
  // For personal teams, TeamList always shows edit (the team owner is always viewing their own teams)
  const shouldShowEdit = (team: Team) => {
    if (isPublicTeam(team)) return false
    if (isSharedTeam(team)) return false
    if (isGroupTeam(team)) {
      return canEditGroupResource(team.namespace!)
    }
    return true
  }

  // Check if delete/unbind button should be shown
  const shouldShowDelete = (team: Team) => {
    // Public teams cannot be deleted by regular users (managed by admin)
    if (isPublicTeam(team)) return false
    // For group teams, check group permissions
    if (isGroupTeam(team)) {
      return canDeleteGroupResource(team.namespace!)
    }
    // For personal teams, always show
    return true
  }

  // Check if share button should be shown
  const shouldShowShare = (team: Team) => {
    // Public teams don't support sharing (they're already globally available)
    if (isPublicTeam(team)) return false
    // Group teams don't support sharing (for now)
    if (isGroupTeam(team)) return false
    // Personal teams (no share_status or share_status=0 or share_status=1) show share button
    return !team.share_status || team.share_status === 0 || team.share_status === 1
  }

  // Check if copy button should be shown (same permission as create)
  const shouldShowCopy = (team: Team) => {
    // For public teams, copy is allowed for personal use
    if (isPublicTeam(team)) return true
    // For group teams, check group permissions (need create permission)
    if (isGroupTeam(team)) {
      return canDeleteGroupResource(team.namespace!) // Maintainer/Owner can create
    }
    // For personal teams, always show
    return true
  }

  return (
    <>
      <div className="flex flex-col h-full min-h-0 overflow-hidden w-full max-w-full">
        <div className="flex-shrink-0 mb-3">
          <h2 className="text-xl font-semibold text-text-primary mb-1">
            {t('common:teams.title')}
          </h2>
          <p className="text-sm text-text-muted mb-1">{t('common:teams.description')}</p>
        </div>
        <div className="bg-base border border-border rounded-md p-2 w-full max-w-full overflow-hidden max-h-[70vh] flex flex-col overflow-y-auto custom-scrollbar">
          {/* Mode filter tabs */}
          <div className="flex items-center gap-1 mb-3 pb-2 border-b border-border">
            <button
              type="button"
              onClick={() => setModeFilter('all')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                modeFilter === 'all'
                  ? 'bg-primary text-white'
                  : 'bg-muted text-text-secondary hover:text-text-primary hover:bg-hover'
              }`}
            >
              {t('common:teams.filter_all')}
            </button>
            <button
              type="button"
              onClick={() => setModeFilter('chat')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                modeFilter === 'chat'
                  ? 'bg-primary text-white'
                  : 'bg-muted text-text-secondary hover:text-text-primary hover:bg-hover'
              }`}
            >
              <ChatBubbleLeftEllipsisIcon className="w-4 h-4" />
              {t('common:teams.filter_chat')}
            </button>
            <button
              type="button"
              onClick={() => setModeFilter('code')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                modeFilter === 'code'
                  ? 'bg-primary text-white'
                  : 'bg-muted text-text-secondary hover:text-text-primary hover:bg-hover'
              }`}
            >
              <CodeBracketIcon className="w-4 h-4" />
              {t('common:teams.filter_code')}
            </button>
          </div>
          {isLoading ? (
            <LoadingState fullScreen={false} message={t('common:teams.loading')} />
          ) : (
            <>
              <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar space-y-3 p-1">
                {filteredTeams.length > 0 ? (
                  filteredTeams.map(team => (
                    <Card
                      key={team.id}
                      className="p-3 sm:p-4 bg-base hover:bg-hover transition-colors overflow-hidden"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-0 min-w-0">
                        <ResourceListItem
                          name={team.name}
                          description={team.description}
                          icon={
                            <TeamIconDisplay
                              iconId={team.icon}
                              size="md"
                              className="text-primary"
                            />
                          }
                          tags={[
                            ...(isPublicTeam(team)
                              ? [
                                  {
                                    key: 'public',
                                    label: t('common:teams.public'),
                                    variant: 'default' as const,
                                  },
                                ]
                              : []),
                            ...(team.workflow?.mode
                              ? [
                                  {
                                    key: 'mode',
                                    label: t(`team_model.${String(team.workflow.mode)}`),
                                    variant: 'default' as const,
                                    className: 'capitalize text-xs',
                                  },
                                ]
                              : []),
                            ...(team.share_status === 1
                              ? [
                                  {
                                    key: 'sharing',
                                    label: t('common:teams.sharing'),
                                    variant: 'info' as const,
                                  },
                                ]
                              : []),
                            ...(team.share_status === 2 && team.user?.user_name
                              ? [
                                  {
                                    key: 'shared',
                                    label: t('common:teams.shared_by', {
                                      author: team.user.user_name,
                                    }),
                                    variant: 'success' as const,
                                  },
                                ]
                              : []),
                            ...(team.bots.length > 0
                              ? [
                                  {
                                    key: 'bots',
                                    label: `${team.bots.length} ${team.bots.length === 1 ? 'Bot' : 'Bots'}`,
                                    variant: 'info' as const,
                                    className: 'hidden sm:inline-flex text-xs',
                                  },
                                ]
                              : []),
                          ]}
                        >
                          <div className="flex items-center space-x-1 flex-shrink-0">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{
                                backgroundColor: team.is_active
                                  ? 'rgb(var(--color-success))'
                                  : 'rgb(var(--color-border))',
                              }}
                            ></div>
                            <span className="text-xs text-text-muted">
                              {team.is_active
                                ? t('common:teams.active')
                                : t('common:teams.inactive')}
                            </span>
                          </div>
                        </ResourceListItem>
                        <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0 sm:ml-3 self-end sm:self-auto">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleChatTeam(team)}
                            title={
                              getTargetPage(team) === 'code'
                                ? t('common:teams.go_to_code')
                                : t('common:teams.go_to_chat')
                            }
                            className="h-7 w-7 sm:h-8 sm:w-8"
                          >
                            {getTargetPage(team) === 'code' ? (
                              <CodeBracketIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            ) : (
                              <ChatBubbleLeftEllipsisIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            )}
                          </Button>
                          {shouldShowEdit(team) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleEditTeam(team)}
                              title={t('common:teams.edit')}
                              className="h-7 w-7 sm:h-8 sm:w-8"
                            >
                              <PencilIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            </Button>
                          )}
                          {shouldShowCopy(team) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleCopyTeam(team)}
                              title={t('common:teams.copy')}
                              className="h-7 w-7 sm:h-8 sm:w-8"
                            >
                              <DocumentDuplicateIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            </Button>
                          )}
                          {shouldShowShare(team) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleShareTeam(team)}
                              title={t('common:teams.share.title')}
                              className="h-7 w-7 sm:h-8 sm:w-8"
                              disabled={sharingId === team.id}
                            >
                              <ShareIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            </Button>
                          )}
                          {/* IM Channel Binding Dropdown - only for personal teams */}
                          {scope === 'personal' && !isPublicTeam(team) && !isGroupTeam(team) && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  title={t('settings:im_bindings.title')}
                                  className="h-7 w-7 sm:h-8 sm:w-8"
                                  disabled={isLoadingBindings}
                                  data-testid={`binding-dropdown-${team.id}`}
                                >
                                  <LinkIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="w-64">
                                <DropdownMenuLabel>
                                  {t('settings:im_bindings.title')}
                                </DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                {(() => {
                                  const teamBindings = getTeamBindings(team.id)
                                  const hasBindings = teamBindings.length > 0
                                  const privateBinding = teamBindings.find(
                                    b => b.private_team_id === team.id
                                  )
                                  const groupBindings = teamBindings.flatMap(b =>
                                    b.group_bindings
                                      .filter(g => g.team_id === team.id)
                                      .map(g => ({
                                        ...g,
                                        channel_id: b.channel_id,
                                        channel_name: b.channel_name,
                                      }))
                                  )

                                  return (
                                    <>
                                      {/* Current Bindings Section */}
                                      {hasBindings ? (
                                        <>
                                          <div className="px-2 py-1.5 text-xs text-text-muted">
                                            {t('settings:teams.bindings.current_bindings')}
                                          </div>
                                          {/* Private binding */}
                                          {privateBinding && (
                                            <DropdownMenuItem
                                              onClick={() =>
                                                handleUnbindPrivate(privateBinding.channel_id)
                                              }
                                              className="flex items-center justify-between"
                                            >
                                              <span className="truncate">
                                                {privateBinding.channel_name} (
                                                {t('settings:teams.bindings.private')})
                                              </span>
                                              <span className="text-xs text-error ml-2">
                                                {t('settings:teams.bindings.unbind')}
                                              </span>
                                            </DropdownMenuItem>
                                          )}
                                          {/* Group bindings */}
                                          {groupBindings.map(group => (
                                            <DropdownMenuItem
                                              key={group.conversation_id}
                                              onClick={() =>
                                                handleUnbindGroup(
                                                  group.channel_id,
                                                  group.conversation_id
                                                )
                                              }
                                              className="flex items-center justify-between"
                                            >
                                              <span className="truncate">
                                                {group.group_name} (
                                                {t('settings:teams.bindings.group')})
                                              </span>
                                              <span className="text-xs text-error ml-2">
                                                {t('settings:teams.bindings.unbind')}
                                              </span>
                                            </DropdownMenuItem>
                                          ))}
                                          <DropdownMenuSeparator />
                                        </>
                                      ) : null}

                                      {/* Bind to Private Section */}
                                      {(() => {
                                        const availableChannels = getAvailableChannelsForBinding(
                                          team.id
                                        )
                                        if (availableChannels.length === 0) return null
                                        return (
                                          <>
                                            <div className="px-2 py-1.5 text-xs text-text-muted">
                                              {t('settings:teams.bindings.bind_to_private')}
                                            </div>
                                            {availableChannels.map(channel => (
                                              <DropdownMenuItem
                                                key={channel.channel_id}
                                                onClick={() =>
                                                  handleBindToPrivate(channel.channel_id, team.id)
                                                }
                                              >
                                                <span className="truncate">
                                                  {channel.channel_name}
                                                </span>
                                              </DropdownMenuItem>
                                            ))}
                                          </>
                                        )
                                      })()}

                                      {/* Bind to Group Section */}
                                      {(() => {
                                        // Get all channels that have groups (bound or unbound)
                                        const channelsWithGroups = imBindings.filter(
                                          binding => binding.group_bindings.length > 0
                                        )
                                        if (channelsWithGroups.length === 0) return null

                                        return (
                                          <>
                                            <DropdownMenuSeparator />
                                            <div className="px-2 py-1.5 text-xs text-text-muted">
                                              {t('settings:teams.bindings.bind_to_group')}
                                            </div>
                                            {channelsWithGroups.map(channel => (
                                              <div key={channel.channel_id}>
                                                <div className="px-2 py-1 text-xs font-medium text-text-secondary">
                                                  {channel.channel_name}
                                                </div>
                                                {channel.group_bindings.map(group => {
                                                  const isBoundToCurrent = group.team_id === team.id
                                                  const boundTeam = teams.find(
                                                    t => t.id === group.team_id
                                                  )
                                                  const boundTeamName =
                                                    boundTeam?.name ||
                                                    t('settings:teams.bindings.unknown_team')

                                                  return (
                                                    <DropdownMenuItem
                                                      key={group.conversation_id}
                                                      onClick={() => {
                                                        if (isBoundToCurrent) {
                                                          // Already bound to current, do nothing or show unbind
                                                          handleUnbindGroup(
                                                            channel.channel_id,
                                                            group.conversation_id
                                                          )
                                                        } else if (group.team_id) {
                                                          // Bound to another team, show switch confirmation
                                                          openSwitchBindingDialog(
                                                            channel.channel_id,
                                                            group.conversation_id,
                                                            group.group_name,
                                                            boundTeamName,
                                                            team.id
                                                          )
                                                        } else {
                                                          // Not bound, bind directly
                                                          handleBindToGroup(
                                                            channel.channel_id,
                                                            group.conversation_id,
                                                            team.id,
                                                            group.group_name
                                                          )
                                                        }
                                                      }}
                                                      className="flex items-center justify-between"
                                                    >
                                                      <span className="truncate">
                                                        {group.group_name}
                                                      </span>
                                                      <span className="text-xs ml-2 flex-shrink-0">
                                                        {isBoundToCurrent ? (
                                                          <span className="text-success">
                                                            ✓{' '}
                                                            {t(
                                                              'settings:teams.bindings.bound_to_current'
                                                            )}
                                                          </span>
                                                        ) : group.team_id ? (
                                                          <span className="text-text-muted">
                                                            {t(
                                                              'settings:teams.bindings.bound_to_other',
                                                              { team: boundTeamName }
                                                            )}
                                                          </span>
                                                        ) : (
                                                          <span className="text-primary">
                                                            {t(
                                                              'settings:teams.bindings.click_to_bind'
                                                            )}
                                                          </span>
                                                        )}
                                                      </span>
                                                    </DropdownMenuItem>
                                                  )
                                                })}
                                              </div>
                                            ))}
                                          </>
                                        )
                                      })()}

                                      {!hasBindings &&
                                        getAvailableChannelsForBinding(team.id).length === 0 &&
                                        imBindings.every(b => b.group_bindings.length === 0) && (
                                          <div className="px-2 py-1.5 text-xs text-text-muted">
                                            {t('settings:teams.bindings.no_bindings_available')}
                                          </div>
                                        )}
                                    </>
                                  )
                                })()}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}
                          {shouldShowDelete(team) && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDelete(team.id)}
                              disabled={isCheckingTasks}
                              title={
                                isSharedTeam(team)
                                  ? t('common:teams.unbind')
                                  : t('common:teams.delete')
                              }
                              className="h-7 w-7 sm:h-8 sm:w-8 hover:text-error"
                            >
                              {isSharedTeam(team) ? (
                                <LinkSlashIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                              ) : (
                                <TrashIcon className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                              )}
                            </Button>
                          )}
                        </div>
                      </div>
                    </Card>
                  ))
                ) : (
                  <div className="text-center text-text-muted py-8">
                    <p className="text-sm">{t('common:teams.no_teams')}</p>
                  </div>
                )}
              </div>
              <div className="border-t border-border pt-3 mt-3 bg-base">
                <div className="flex justify-center gap-3">
                  {(scope === 'personal' || canCreateInCurrentGroup) && (
                    <UnifiedAddButton onClick={handleCreateTeam}>
                      {t('common:teams.new_team')}
                    </UnifiedAddButton>
                  )}
                  {(scope === 'personal' || canCreateInCurrentGroup) && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={handleOpenWizard}
                            className="gap-2"
                          >
                            <SparklesIcon className="w-4 h-4" />
                            {t('wizard:wizard_button')}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>{t('wizard:wizard_button_tooltip')}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                  <UnifiedAddButton
                    variant="outline"
                    onClick={() => setBotListVisible(true)}
                    icon={<RiRobot2Line className="w-4 h-4" />}
                  >
                    {t('bots.manage_bots')}
                  </UnifiedAddButton>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Team Edit Dialog */}
      <TeamEditDialog
        open={editDialogOpen}
        onClose={handleCloseEditDialog}
        teams={teams}
        setTeams={setTeamsSorted}
        editingTeamId={editingTeamId}
        initialTeam={prefillTeam}
        bots={bots}
        setBots={setBotsSorted}
        toast={toast}
        scope={scope}
        groupName={groupName}
      />

      {/* Delete/Unbind confirmation dialog */}
      <Dialog
        open={deleteConfirmVisible}
        onOpenChange={open => !open && !isDeleting && setDeleteConfirmVisible(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {isUnbindingSharedTeam
                ? t('common:teams.unbind_confirm_title')
                : t('common:teams.delete_confirm_title')}
            </DialogTitle>
            <DialogDescription>
              {isUnbindingSharedTeam
                ? t('common:teams.unbind_confirm_message')
                : t('common:teams.delete_confirm_message')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={handleCancelDelete} disabled={isDeleting}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isDeleting}>
              {isDeleting ? (
                <div className="flex items-center">
                  <svg
                    className="animate-spin -ml-1 mr-2 h-4 w-4"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  {t('actions.deleting')}
                </div>
              ) : (
                t('common.confirm')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Force delete confirmation dialog for running tasks */}
      <Dialog
        open={forceDeleteConfirmVisible}
        onOpenChange={open => !open && !isDeleting && setForceDeleteConfirmVisible(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('common:teams.force_delete_confirm_title')}</DialogTitle>
            <DialogDescription>
              {t('common:teams.force_delete_confirm_message', {
                count: runningTasksInfo?.running_tasks_count || 0,
              })}
            </DialogDescription>
          </DialogHeader>
          <ForceDeleteTaskSummary
            runningTasks={runningTasksInfo?.running_tasks || []}
            runningTasksTitle={t('common:teams.running_tasks_list')}
            warning={t('common:teams.force_delete_warning')}
            andMoreLabel={
              runningTasksInfo && runningTasksInfo.running_tasks.length > 5
                ? `... ${t('common:teams.and_more_tasks', {
                    count: runningTasksInfo.running_tasks.length - 5,
                  })}`
                : undefined
            }
          />
          <DialogFooter>
            <Button variant="secondary" onClick={handleCancelDelete} disabled={isDeleting}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleForceDelete} disabled={isDeleting}>
              {isDeleting ? (
                <div className="flex items-center">
                  <svg
                    className="animate-spin -ml-1 mr-2 h-4 w-4"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  {t('actions.deleting')}
                </div>
              ) : (
                t('common:teams.force_delete')
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Switch binding confirmation dialog */}
      <Dialog
        open={switchBindingDialog.open}
        onOpenChange={open => !open && setSwitchBindingDialog(prev => ({ ...prev, open: false }))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings:teams.bindings.switch_binding_title')}</DialogTitle>
            <DialogDescription>
              {t('settings:teams.bindings.switch_binding_message', {
                group_name: switchBindingDialog.groupName,
                current_team: switchBindingDialog.currentTeamName,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setSwitchBindingDialog(prev => ({ ...prev, open: false }))}
            >
              {t('common.cancel')}
            </Button>
            <Button variant="primary" onClick={confirmSwitchBinding}>
              {t('settings:teams.bindings.confirm_switch')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Share success dialog */}
      {shareData && (
        <TeamShareModal
          visible={shareModalVisible}
          onClose={handleCloseShareModal}
          teamName={shareData.teamName}
          shareUrl={shareData.shareUrl}
        />
      )}

      {/* Bot list dialog */}
      <Dialog
        open={botListVisible}
        onOpenChange={open => {
          setBotListVisible(open)
          // Refresh bots list when dialog is closed to sync any changes made in BotList
          if (!open) {
            fetchBotsList(scope, groupName)
              .then(setBotsSorted)
              .catch(() => {})
          }
        }}
      >
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>{t('bots.title')}</DialogTitle>
            <DialogDescription>{t('bots.description')}</DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto">
            <BotList scope={scope} groupName={groupName} groupRoleMap={groupRoleMap} />
          </div>
        </DialogContent>
      </Dialog>

      {/* Team Creation Wizard */}
      <TeamCreationWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onSuccess={handleWizardSuccess}
        scope={scope === 'all' ? undefined : scope}
        groupName={groupName}
      />
      {/* Error prompt unified with antd message, no local rendering */}
    </>
  )
}
