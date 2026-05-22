interface ConversationItemProps {
  title: string
  onClick: () => void
}

export function ConversationItem({ title, onClick }: ConversationItemProps) {
  return (
    <div
      onClick={onClick}
      className="w-full cursor-pointer truncate py-3 text-[17px] text-black"
      title={title}
    >
      {title}
    </div>
  )
}
