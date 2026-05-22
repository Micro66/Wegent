import { Image, Pencil, Globe } from 'lucide-react'

interface Action {
  icon: React.ReactNode
  label: string
}

const actions: Action[] = [
  { icon: <Image className="h-6 w-6" />, label: '生成图片' },
  { icon: <Pencil className="h-6 w-6" />, label: '撰写或编辑' },
  { icon: <Globe className="h-6 w-6" />, label: '查找资料' },
]

export function QuickActions() {
  return (
    <div className="flex flex-col px-6 pb-4">
      {actions.map((action, i) => (
        <div
          key={i}
          className="flex cursor-pointer items-center gap-4 py-4"
        >
          <span className="text-black">{action.icon}</span>
          <span className="text-[17px] text-black">{action.label}</span>
        </div>
      ))}
    </div>
  )
}
