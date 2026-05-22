import { useMemo, useState } from 'react'
import { Check, Search } from 'lucide-react'
import type { Team } from '@/types/api'

interface Props {
  open: boolean
  onClose: () => void
  teams: Team[]
  selectedTeamId?: number
  onSelectAgent: (teamId: number) => void
}

export function AgentSheet({
  open,
  onClose,
  teams,
  selectedTeamId,
  onSelectAgent,
}: Props) {
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLowerCase()
  const filteredTeams = useMemo(() => {
    if (!normalizedQuery) return teams

    return teams.filter((team) => {
      const name = team.name?.toLowerCase() ?? ''
      const description = team.description?.toLowerCase() ?? ''
      return name.includes(normalizedQuery) || description.includes(normalizedQuery)
    })
  }, [normalizedQuery, teams])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <div className="absolute inset-0 bg-black/30 animate-fade-in" onClick={onClose} />

      <div className="relative flex max-h-[78%] flex-col rounded-t-2xl bg-white shadow-[0_-8px_28px_rgba(0,0,0,0.12)] animate-slide-up">
        <div className="flex justify-center pt-2.5 pb-2">
          <div className="h-1 w-9 rounded-full bg-[#d8d8d8]" />
        </div>

        <h2 className="border-b border-[#eee] px-5 pb-3 text-center text-[17px] font-semibold text-black">
          智能体
        </h2>

        <div className="px-4 pt-3">
          <label className="flex h-11 items-center gap-2 rounded-full border border-[#e5e5e5] bg-[#f7f7f8] px-4">
            <Search className="h-4 w-4 shrink-0 text-[#999]" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              data-testid="agent-search-input"
              placeholder="搜索智能体"
              className="min-w-0 flex-1 bg-transparent text-[15px] text-black placeholder-[#999] outline-none"
            />
          </label>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-2">
          {filteredTeams.length === 0 ? (
            <div className="flex min-h-28 items-center justify-center rounded-xl text-[14px] text-[#999]">
              没有找到智能体
            </div>
          ) : null}

          {filteredTeams.map((team) => {
            const isSelected = team.id === selectedTeamId
            return (
              <button
                type="button"
                key={team.id}
                onClick={() => onSelectAgent(team.id)}
                data-testid={`agent-option-${team.id}`}
                className={`flex min-h-14 w-full items-center gap-3 rounded-xl px-3 py-2 text-left active:bg-[#f5f5f5] ${
                  isSelected ? 'bg-[#f7f7f8]' : 'bg-white'
                }`}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#14B8A6] text-[17px] font-semibold text-white">
                  {team.name?.charAt(0) ?? 'A'}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[16px] font-semibold text-black">
                    {team.name}
                  </div>
                  {team.description ? (
                    <div className="mt-0.5 truncate text-[13px] text-[#999]">
                      {team.description}
                    </div>
                  ) : null}
                </div>
                {isSelected && (
                  <Check className="h-[18px] w-[18px] shrink-0 text-[#14B8A6]" />
                )}
              </button>
            )
          })}
        </div>

      </div>
    </div>
  )
}
