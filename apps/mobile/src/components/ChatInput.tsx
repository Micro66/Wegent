import { useState, useRef, useLayoutEffect } from 'react'
import { Plus, ArrowUp, Square } from 'lucide-react'

interface Props {
  placeholder: string
  isStreaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export function ChatInput({ placeholder, isStreaming, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const [isComposing, setIsComposing] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const resizeTextarea = () => {
    const input = inputRef.current
    if (!input) return

    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`
  }

  useLayoutEffect(() => {
    resizeTextarea()
  }, [text])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isComposing || e.nativeEvent.isComposing || e.keyCode === 229) return

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="px-4 pb-5 pt-3">
      <div className="flex items-center gap-2 rounded-[28px] border border-[#eee] bg-white px-2 py-1.5 shadow-[0_2px_12px_rgba(0,0,0,0.08)]">
        <button
          type="button"
          data-testid="add-attachment-button"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#999]"
        >
          <Plus className="h-5 w-5" />
        </button>

        <textarea
          ref={inputRef}
          value={text}
          onChange={e => setText(e.target.value)}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          className="max-h-[132px] min-h-9 flex-1 resize-none overflow-y-auto bg-transparent py-2 text-[15px] leading-5 text-black placeholder-[#b0b0b0] outline-none"
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            data-testid="stop-button"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black"
          >
            <Square className="h-4 w-4 fill-white text-white" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={!text.trim()}
            data-testid="send-button"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black disabled:bg-[#d4d4d4]"
          >
            <ArrowUp className="h-4 w-4 text-white" />
          </button>
        )}
      </div>
    </div>
  )
}
