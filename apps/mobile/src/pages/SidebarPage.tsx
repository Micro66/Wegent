import { useNavigate } from 'react-router-dom'
import { Search, Plus, LogOut } from 'lucide-react'
import { ConversationItem } from '@/components/ConversationItem'
import { mainNavItems } from '@/components/main-nav-items'
import { useTasks } from '@/hooks/useTasks'
import { useAuth } from '@/hooks/useAuth'

const loadingSkeletonWidths = ['74%', '88%', '66%', '81%', '70%']

export function SidebarPage() {
  const navigate = useNavigate()
  const { tasks, loading } = useTasks()
  const { user, logout } = useAuth()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const recentTasks = tasks.filter(
    (t) => t.status === 'RUNNING' || t.status === 'PENDING',
  )
  const olderTasks = tasks.filter(
    (t) => t.status === 'COMPLETED' || t.status === 'FAILED' || t.status === 'CANCELLED',
  )

  return (
    <div className="flex h-dvh flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <h1 className="text-[28px] font-extrabold tracking-[-0.5px] text-black">
          Wegent
        </h1>
        <div className="flex items-center gap-2 rounded-3xl border border-[#eee] bg-white px-3.5 py-1.5 shadow-[0_2px_10px_rgba(0,0,0,0.06)]">
          <Search className="h-[18px] w-[18px] text-[#999]" />
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-purple-600 to-purple-400 text-[13px] font-bold text-white">
            {user?.user_name?.slice(0, 2).toUpperCase() ?? 'MI'}
          </div>
          <button
            type="button"
            onClick={handleLogout}
            data-testid="logout-button"
            aria-label="退出登录"
            className="flex h-8 w-8 items-center justify-center rounded-full text-[#666] active:bg-[#f0f0f0]"
          >
            <LogOut className="h-[16px] w-[16px]" />
          </button>
        </div>
      </div>

      {/* Main Nav */}
      <div className="flex flex-col px-4 pt-1">
        {mainNavItems.map((item, i) => (
          <div
            key={i}
            className="flex cursor-pointer items-center gap-4 py-4 pl-1"
          >
            <span className="text-black">{item.icon}</span>
            <span className="text-[18px] font-semibold text-black">
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Divider */}
      <div className="mx-4 h-px bg-[#eee]" />

      {/* Recent section header */}
      <div className="px-5 pt-4 pb-1">
        <span className="text-[14px] font-semibold uppercase tracking-[0.5px] text-[#999]">
          最近
        </span>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-5 pb-20">
        {loading ? (
          <div className="space-y-4 pt-4">
            {loadingSkeletonWidths.map((width) => (
              <div
                key={width}
                className="h-5 animate-pulse rounded bg-[#f0f0f0]"
                style={{ width }}
              />
            ))}
          </div>
        ) : tasks.length === 0 ? (
          <p className="py-8 text-center text-[15px] text-[#999]">暂无会话</p>
        ) : (
          <>
            {recentTasks.map((task) => (
              <ConversationItem
                key={task.id}
                title={task.title}
                onClick={() => navigate(`/?task=${task.id}`)}
              />
            ))}
            {olderTasks.map((task) => (
              <ConversationItem
                key={task.id}
                title={task.title}
                onClick={() => navigate(`/?task=${task.id}`)}
              />
            ))}
          </>
        )}
      </div>

      {/* FAB */}
      <div className="absolute bottom-6 right-5">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 rounded-3xl bg-black px-5 py-2.5 text-base font-semibold text-white shadow-[0_4px_16px_rgba(0,0,0,0.2)]"
        >
          <Plus className="h-[18px] w-[18px]" />
          聊天
        </button>
      </div>

    </div>
  )
}
