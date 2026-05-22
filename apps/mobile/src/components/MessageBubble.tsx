import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { UIMessage } from '@/hooks/useChat'
import type { MessageBlock } from '@/types/api'

interface Props {
  message: UIMessage
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-sm max-w-none text-[15px] leading-relaxed text-black">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded-lg bg-[#f5f5f5] p-3 text-[13px] leading-snug">
              {children}
            </pre>
          ),
          code: ({ className, children, ...props }) => {
            const isInline = !className
            if (isInline) {
              return (
                <code className="rounded bg-[#f0f0f0] px-1 py-0.5 text-[13px]" {...props}>
                  {children}
                </code>
              )
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            )
          },
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="min-w-full border-collapse border border-[#e0e0e0] text-[13px]">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-[#e0e0e0] bg-[#f5f5f5] px-3 py-1.5 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-[#e0e0e0] px-3 py-1.5">{children}</td>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#14B8A6] underline"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => <ul className="my-1 list-disc pl-5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 list-decimal pl-5">{children}</ol>,
          h1: ({ children }) => <h1 className="my-2 text-[18px] font-bold">{children}</h1>,
          h2: ({ children }) => <h2 className="my-2 text-[17px] font-bold">{children}</h2>,
          h3: ({ children }) => <h3 className="my-1.5 text-[16px] font-semibold">{children}</h3>,
          p: ({ children }) => <p className="my-1">{children}</p>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function ThinkingPanel({
  reasoningContent,
  thinking,
  defaultOpen = false,
}: {
  reasoningContent?: string
  thinking?: unknown[]
  defaultOpen?: boolean
}) {
  const thinkingText = thinking?.length
    ? thinking
        .map(item => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object') {
            const record = item as Record<string, unknown>
            return (
              [record.title, record.action, record.reasoning, record.result]
                .filter(value => typeof value === 'string' && value.trim())
                .join('\n') || JSON.stringify(item)
            )
          }
          return ''
        })
        .filter(Boolean)
        .join('\n\n')
    : ''
  const content = reasoningContent || thinkingText

  if (!content.trim()) return null

  return (
    <details
      open={defaultOpen}
      className="mb-2 rounded-xl border border-[#e8e8e8] bg-[#fafafa] px-3 py-2 text-[13px] text-[#666]"
    >
      <summary className="cursor-pointer select-none font-medium text-[#555]">
        思考过程
      </summary>
      <div className="mt-2 whitespace-pre-wrap leading-relaxed">{content}</div>
    </details>
  )
}

function ToolBlock({ block }: { block: MessageBlock }) {
  const title = block.display_name || block.tool_name || '工具调用'
  const output =
    typeof block.tool_output === 'string'
      ? block.tool_output
      : block.tool_output
        ? JSON.stringify(block.tool_output, null, 2)
        : ''

  return (
    <details className="my-2 rounded-xl border border-[#e8e8e8] bg-[#fafafa] px-3 py-2 text-[13px]">
      <summary className="cursor-pointer select-none font-medium text-[#555]">
        {title}
        {block.status ? <span className="ml-1 text-[#999]">· {block.status}</span> : null}
      </summary>
      {block.tool_input ? (
        <pre className="mt-2 overflow-x-auto rounded-lg bg-white p-2 text-[12px] text-[#555]">
          {JSON.stringify(block.tool_input, null, 2)}
        </pre>
      ) : null}
      {output ? (
        <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-white p-2 text-[12px] text-[#555]">
          {output}
        </pre>
      ) : null}
    </details>
  )
}

function MessageBlockView({ block }: { block: MessageBlock }) {
  if (block.type === 'text') {
    return block.content ? <Markdown content={block.content} /> : null
  }

  if (block.type === 'thinking') {
    return <ThinkingPanel reasoningContent={block.content} />
  }

  if (block.type === 'tool') {
    return <ToolBlock block={block} />
  }

  if (block.type === 'image' && block.image_urls?.length) {
    return (
      <div className="my-2 grid grid-cols-2 gap-2">
        {block.image_urls.map(url => (
          <img key={url} src={url} alt="" className="rounded-xl border border-[#eee]" />
        ))}
      </div>
    )
  }

  if (block.type === 'video' && block.video_url) {
    return (
      <video
        src={block.video_url}
        controls
        className="my-2 w-full rounded-xl border border-[#eee]"
      />
    )
  }

  return block.content ? <Markdown content={block.content} /> : null
}

function MixedContent({ message }: { message: UIMessage }) {
  const blocks = message.result?.blocks ?? []
  const hasBlocks = blocks.length > 0
  const hasTextBlock = blocks.some(block => block.type === 'text')
  const isStreaming = message.status === 'streaming'

  return (
    <>
      <ThinkingPanel
        reasoningContent={message.reasoningContent ?? message.result?.reasoning_content}
        thinking={message.result?.thinking}
        defaultOpen={isStreaming}
      />
      {hasBlocks
        ? blocks.map((block, index) => (
            <MessageBlockView key={block.id ?? `${block.type}-${index}`} block={block} />
          ))
        : null}
      {(!hasBlocks || (!hasTextBlock && message.content.trim())) && (
        <Markdown content={message.content} />
      )}
    </>
  )
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
    <div className="px-4 py-2">
      <MixedContent message={message} />
      {message.status === 'streaming' && (
        <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-black" />
      )}
      {message.status === 'error' && (
        <p className="mt-1 text-xs text-red-500">{message.error}</p>
      )}
    </div>
  )
}
