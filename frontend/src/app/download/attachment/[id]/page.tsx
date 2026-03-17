'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { FileIcon, Download, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserProvider, useUser } from '@/features/common/UserContext'

const API_BASE_URL = ''

function getToken(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/wegent-token=([^;]+)/)
  return match ? match[1] : null
}

interface AttachmentInfo {
  id: number
  filename: string
  mime_type: string
  file_size?: number
}

// Inner component that uses useUser
function AttachmentDownloadContent() {
  const { id } = useParams()
  const router = useRouter()
  const { user, isLoading: authLoading } = useUser()
  const [attachmentInfo, setAttachmentInfo] = useState<AttachmentInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadComplete, setDownloadComplete] = useState(false)

  const attachmentId = Array.isArray(id) ? id[0] : id

  const isAuthenticated = !!user

  useEffect(() => {
    // Wait for auth state to be determined
    if (authLoading) return

    if (!isAuthenticated) {
      // Not logged in, redirect to login with return URL
      const currentUrl = window.location.href
      router.push(`/login?redirect=${encodeURIComponent(currentUrl)}`)
      return
    }

    // Logged in, fetch attachment info and auto download
    fetchAttachmentInfoAndDownload()
  }, [isAuthenticated, authLoading, attachmentId])

  const fetchAttachmentInfoAndDownload = async () => {
    try {
      setLoading(true)
      const token = getToken()

      // Fetch attachment details from backend
      const response = await fetch(`${API_BASE_URL}/api/attachments/${attachmentId}`, {
        headers: {
          ...(token && { Authorization: `Bearer ${token}` }),
        },
      })

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('附件不存在或已被删除')
        }
        if (response.status === 403) {
          throw new Error('没有权限访问此附件')
        }
        throw new Error('获取附件信息失败')
      }

      const data = await response.json()
      const info = {
        id: data.id,
        filename: data.original_filename || data.filename,
        mime_type: data.mime_type,
        file_size: data.file_size,
      }
      setAttachmentInfo(info)

      // Auto download after getting attachment info
      await downloadFile(info.filename, token)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取附件信息失败')
    } finally {
      setLoading(false)
    }
  }

  const downloadFile = async (filename?: string, token?: string | null) => {
    try {
      setDownloading(true)

      // Fetch the file from backend
      const response = await fetch(`${API_BASE_URL}/api/attachments/${attachmentId}/download`, {
        headers: {
          ...(token && { Authorization: `Bearer ${token}` }),
        },
      })

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('附件不存在或已被删除')
        }
        if (response.status === 403) {
          throw new Error('没有权限下载此附件')
        }
        throw new Error('下载失败')
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('Content-Disposition')
      let downloadFilename = filename || 'download'
      if (contentDisposition) {
        const match = contentDisposition.match(/filename\*?=['"]?([^'"]+)['"]?/)
        if (match) {
          downloadFilename = decodeURIComponent(match[1].replace("UTF-8''", ''))
        }
      }

      // Create blob and download
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadFilename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      setDownloadComplete(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载失败')
    } finally {
      setDownloading(false)
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-gray-600">加载中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 mx-auto text-red-500 mb-4" />
          <h1 className="text-xl font-semibold mb-2">下载失败</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <Button onClick={() => router.push('/chat')}>返回首页</Button>
        </div>
      </div>
    )
  }

  if (!attachmentInfo) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 mx-auto text-red-500 mb-4" />
          <h1 className="text-xl font-semibold mb-2">附件不存在</h1>
          <p className="text-gray-600 mb-6">无法找到此附件信息</p>
          <Button onClick={() => router.push('/chat')}>返回首页</Button>
        </div>
      </div>
    )
  }

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return ''
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    }
    if (bytes >= 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`
    }
    return `${bytes} bytes`
  }

  // Show downloading state
  if (downloading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <div className="mb-6">
            <Loader2 className="w-20 h-20 mx-auto text-primary animate-spin" />
          </div>
          <h1 className="text-xl font-semibold mb-2">正在下载...</h1>
          <p className="text-gray-500 text-sm break-all">{attachmentInfo.filename}</p>
        </div>
      </div>
    )
  }

  // Show success state
  if (downloadComplete) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <div className="mb-6">
            <FileIcon className="w-20 h-20 mx-auto text-green-500" />
          </div>
          <h1 className="text-xl font-semibold mb-2 text-green-600">下载已开始</h1>
          <p className="text-gray-500 text-sm break-all mb-4">{attachmentInfo.filename}</p>
          <p className="text-xs text-gray-400">如果下载没有自动开始，请点击下方按钮</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Button variant="outline" onClick={() => router.push('/chat')}>
              返回首页
            </Button>
            <Button onClick={() => downloadFile(attachmentInfo.filename, getToken())}>
              <Download className="w-4 h-4 mr-2" />
              重新下载
            </Button>
          </div>
        </div>
      </div>
    )
  }

  // Default: show file info with manual download button
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-lg p-8 max-w-md w-full text-center">
        <div className="mb-6">
          <FileIcon className="w-20 h-20 mx-auto text-primary" />
        </div>

        <h1 className="text-xl font-semibold mb-2 break-all">{attachmentInfo.filename}</h1>
        <p className="text-gray-500 text-sm mb-2">{attachmentInfo.mime_type}</p>
        {attachmentInfo.file_size && (
          <p className="text-gray-400 text-xs mb-6">{formatFileSize(attachmentInfo.file_size)}</p>
        )}

        <Button
          size="lg"
          className="w-full"
          onClick={() => downloadFile(attachmentInfo.filename, getToken())}
        >
          <Download className="w-5 h-5 mr-2" />
          下载文件
        </Button>
      </div>
    </div>
  )
}

// Main export with UserProvider wrapper
export default function AttachmentDownloadPage() {
  return (
    <UserProvider>
      <AttachmentDownloadContent />
    </UserProvider>
  )
}
