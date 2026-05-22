import { Menu } from 'lucide-react'

interface Props {
  agentName: string
  modelName?: string
  onMenuClick: () => void
  onAgentClick: () => void
}

export function ChatHeader({ agentName, modelName, onMenuClick, onAgentClick }: Props) {
  return (
    <div className="flex items-center gap-3 px-4 pt-3 pb-2">
      <button
        onClick={onMenuClick}
        data-testid="chat-menu-button"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f0f0f0]"
      >
        <Menu className="h-5 w-5 text-[#333]" />
      </button>

      <button
        onClick={onAgentClick}
        data-testid="chat-agent-selector"
        className="flex h-10 max-w-[220px] items-center rounded-full border border-[#e0e0e0] bg-white px-4 text-left shadow-[0_1px_3px_rgba(0,0,0,0.04)]"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-bold leading-[17px] text-black">
            {agentName}
          </span>
          {modelName ? (
            <span className="block truncate text-[10px] font-medium leading-[12px] text-[#999]">
              {modelName}
            </span>
          ) : null}
        </span>
        <span className="ml-1 text-[10px] text-[#999]">▾</span>
      </button>

      <div className="flex-1" />
    </div>
  )
}
