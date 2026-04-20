// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

type GroupChatTeamIdentity = {
  id: number
  name: string
  icon?: string | null
}

type ResolveGroupChatAgentIdentityParams = {
  teamId?: number | null
  fallbackName?: string
  fallbackIcon?: string | null
  groupChatTeams?: GroupChatTeamIdentity[]
}

export type GroupChatAgentIdentity = {
  teamId?: number
  botName?: string
  botIcon?: string | null
}

export function resolveGroupChatAgentIdentity({
  teamId,
  fallbackName,
  fallbackIcon,
  groupChatTeams = [],
}: ResolveGroupChatAgentIdentityParams): GroupChatAgentIdentity {
  if (teamId != null) {
    const matchedTeam = groupChatTeams.find(team => team.id === teamId)
    if (matchedTeam) {
      return {
        teamId: matchedTeam.id,
        botName: matchedTeam.name,
        botIcon: matchedTeam.icon,
      }
    }
  }

  return {
    teamId: teamId ?? undefined,
    botName: fallbackName,
    botIcon: fallbackIcon,
  }
}
