import { Menu, Sparkles } from 'lucide-react'

interface Props {
  agentName: string
  onMenuClick: () => void
  onAgentClick: () => void
}

export function ChatHeader({ agentName, onMenuClick, onAgentClick }: Props) {
  return (
    <div className="flex items-center gap-3 px-4 pt-3 pb-2">
      <button
        onClick={onMenuClick}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f0f0f0]"
      >
        <Menu className="h-5 w-5 text-[#333]" />
      </button>

      <button
        onClick={onAgentClick}
        className="rounded-full border border-[#e0e0e0] bg-white px-5 py-2 text-[15px] font-bold text-black shadow-[0_1px_3px_rgba(0,0,0,0.04)]"
      >
        {agentName}{' '}
        <span className="ml-1 text-[10px] text-[#999]">▾</span>
      </button>

      <div className="flex-1" />

      <button className="flex h-10 w-10 items-center justify-center rounded-full">
        <Sparkles className="h-6 w-6 text-black" />
      </button>
    </div>
  )
}
