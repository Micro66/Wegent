import type { UIMessage } from '@/hooks/useChat'

interface Props {
  message: UIMessage
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1.5">
        <div className="max-w-[80%] rounded-2xl bg-black px-4 py-2.5 text-[15px] leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 px-4 py-1.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#14B8A6] text-sm text-white">
        {message.botName?.charAt(0) ?? 'A'}
      </div>
      <div className="max-w-[80%] rounded-2xl bg-[#f0f0f0] px-4 py-2.5 text-[15px] leading-relaxed text-black">
        {message.content}
        {message.status === 'streaming' && (
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-black" />
        )}
        {message.status === 'error' && (
          <p className="mt-1 text-xs text-red-500">{message.error}</p>
        )}
      </div>
    </div>
  )
}
