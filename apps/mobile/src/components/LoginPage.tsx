import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

export function LoginPage() {
  const navigate = useNavigate()
  const { login, loading, error, user } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (user) {
      navigate('/', { replace: true })
    }
  }, [navigate, user])

  if (user) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void login(username, password)
  }

  return (
    <div className="flex h-dvh flex-col items-center justify-center bg-white px-8">
      <div className="mb-12 flex h-20 w-20 items-center justify-center rounded-2xl bg-black text-3xl font-bold text-white">
        W
      </div>
      <h1 className="mb-8 text-2xl font-bold text-black">登录 Wegent</h1>

      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <input
          type="text"
          placeholder="用户名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full rounded-xl border border-[#e0e0e0] bg-[#f5f5f5] px-4 py-3 text-[16px] text-black placeholder-[#999] outline-none focus:border-black"
        />
        <input
          type="password"
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-xl border border-[#e0e0e0] bg-[#f5f5f5] px-4 py-3 text-[16px] text-black placeholder-[#999] outline-none focus:border-black"
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={loading || !username || !password}
          className="w-full rounded-xl bg-black py-3 text-[16px] font-semibold text-white disabled:opacity-50"
        >
          {loading ? '登录中...' : '登录'}
        </button>
      </form>
    </div>
  )
}
