import { useState, useRef } from 'react'
import { Plus, Mic, ArrowUp, Square } from 'lucide-react'

interface Props {
  placeholder: string
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export function ChatInput({ placeholder, isStreaming, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="px-4 pb-5 pt-3">
      <div className="flex items-end gap-2 rounded-[28px] border border-[#eee] bg-white px-2 py-1.5 shadow-[0_2px_12px_rgba(0,0,0,0.08)]">
        <button className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#999]">
          <Plus className="h-5 w-5" />
        </button>

        <textarea
          ref={inputRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="flex-1 resize-none bg-transparent py-1.5 text-[15px] text-black placeholder-[#b0b0b0] outline-none"
        />

        {isStreaming ? (
          <button
            onClick={onStop}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black"
          >
            <Square className="h-4 w-4 fill-white text-white" />
          </button>
        ) : (
          <>
            <button className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#999]">
              <Mic className="h-4 w-4" />
            </button>
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black disabled:bg-[#d4d4d4]"
            >
              <ArrowUp className="h-4 w-4 text-white" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}
