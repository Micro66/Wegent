# File Preview Reuse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract the file preview functionality from `/download/shared` page into reusable components that can be used in both the shared download page and task file pages.

**Architecture:** Create a modular `FilePreview` component system with separate renderers for each file type (image, PDF, text, video, audio, Excel, Word/PPT). Support both fullscreen page mode and dialog/inline embedding modes.

**Tech Stack:** React, TypeScript, Tailwind CSS, SheetJS (xlsx), Lucide React icons

---

## Task 1: Create File Preview Utilities

**Files:**
- Create: `frontend/src/components/common/FilePreview/utils.ts`

**Step 1: Create utility functions**

Create the file with type detection and formatting utilities extracted from `/download/shared/page.tsx`:

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

export type PreviewType = 'image' | 'pdf' | 'text' | 'video' | 'audio' | 'office' | 'unknown'

/**
 * Determine preview type based on MIME type and filename
 */
export function getPreviewType(mimeType: string, filename: string): PreviewType {
  if (mimeType.startsWith('image/')) return 'image'
  if (mimeType === 'application/pdf') return 'pdf'
  if (mimeType.startsWith('video/')) return 'video'
  if (mimeType.startsWith('audio/')) return 'audio'
  if (
    mimeType.startsWith('text/') ||
    mimeType === 'application/json' ||
    mimeType === 'application/javascript' ||
    mimeType === 'application/typescript' ||
    mimeType === 'application/xml' ||
    filename.match(
      /\.(txt|md|json|js|ts|jsx|tsx|py|java|go|rs|cpp|c|h|hpp|css|scss|less|html|htm|xml|yaml|yml|sh|bash|zsh|ps1|sql|log)$/i
    )
  ) {
    return 'text'
  }
  if (
    mimeType.includes('officedocument') ||
    mimeType.includes('msword') ||
    mimeType.includes('ms-excel') ||
    mimeType.includes('ms-powerpoint') ||
    mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ) {
    return 'office'
  }
  return 'unknown'
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/**
 * Get Office document type
 */
export function getOfficeType(filename: string): 'excel' | 'word' | 'powerpoint' {
  const ext = filename.toLowerCase()
  if (ext.match(/\.(xlsx|xls|csv)$/)) return 'excel'
  if (ext.match(/\.(pptx|ppt)$/)) return 'powerpoint'
  return 'word'
}

/**
 * Check if filename is a code file
 */
export function isCodeFile(filename: string): boolean {
  return /\.(js|ts|jsx|tsx|py|java|go|rs|cpp|c|h|hpp|css|scss|less|html|htm|xml|json|yaml|yml|sh|bash|zsh|ps1|sql)$/i.test(
    filename
  )
}
```

**Step 2: Verify file is created**

Run: `ls -la frontend/src/components/common/FilePreview/`
Expected: `utils.ts` exists

**Step 3: Commit**

```bash
git add frontend/src/components/common/FilePreview/utils.ts
git commit -m "feat: add file preview utility functions"
```

---

## Task 2: Create Excel Parser Hook

**Files:**
- Create: `frontend/src/components/common/FilePreview/hooks/useExcelParser.ts`

**Step 1: Create the hook**

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { useState, useCallback } from 'react'
import * as XLSX from 'xlsx'

export interface ExcelSheet {
  name: string
  data: (string | number | boolean | null)[][]
}

interface UseExcelParserReturn {
  sheets: ExcelSheet[]
  isLoading: boolean
  error: string | null
  parseExcel: (blob: Blob) => Promise<void>
}

/**
 * Hook for parsing Excel files using SheetJS
 */
export function useExcelParser(): UseExcelParserReturn {
  const [sheets, setSheets] = useState<ExcelSheet[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const parseExcel = useCallback(async (blob: Blob) => {
    setIsLoading(true)
    setError(null)

    try {
      const arrayBuffer = await blob.arrayBuffer()
      const workbook = XLSX.read(arrayBuffer, { type: 'array' })
      const parsedSheets: ExcelSheet[] = []

      for (const sheetName of workbook.SheetNames) {
        const worksheet = workbook.Sheets[sheetName]
        const jsonData = XLSX.utils.sheet_to_json(worksheet, {
          header: 1,
          defval: '',
          blankrows: false,
        }) as (string | number | boolean | null)[][]

        parsedSheets.push({
          name: sheetName,
          data: jsonData,
        })
      }

      setSheets(parsedSheets)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to parse Excel file'
      setError(errorMessage)
      setSheets([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  return { sheets, isLoading, error, parseExcel }
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/hooks/useExcelParser.ts
git commit -m "feat: add useExcelParser hook for Excel file preview"
```

---

## Task 3: Create useFileBlob Hook

**Files:**
- Create: `frontend/src/components/common/FilePreview/hooks/useFileBlob.ts`

**Step 1: Create the hook**

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { useState, useEffect, useCallback } from 'react'
import { getToken } from '@/apis/user'
import { getAttachmentDownloadUrl } from '@/apis/attachments'

interface UseFileBlobReturn {
  blob: Blob | null
  blobUrl: string | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Hook for fetching file blob from attachment ID or using provided blob
 */
export function useFileBlob(
  attachmentId?: number,
  externalBlob?: Blob,
  shareToken?: string
): UseFileBlobReturn {
  const [blob, setBlob] = useState<Blob | null>(externalBlob || null)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(!externalBlob && !!attachmentId)
  const [error, setError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  const refetch = useCallback(() => {
    setRetryKey(prev => prev + 1)
  }, [])

  useEffect(() => {
    // If external blob is provided, use it directly
    if (externalBlob) {
      setBlob(externalBlob)
      const url = URL.createObjectURL(externalBlob)
      setBlobUrl(url)
      setIsLoading(false)
      return
    }

    // If no attachmentId, reset state
    if (!attachmentId) {
      setBlob(null)
      setBlobUrl(null)
      setIsLoading(false)
      return
    }

    let isMounted = true
    let currentBlobUrl: string | null = null

    const fetchBlob = async () => {
      setIsLoading(true)
      setError(null)

      try {
        const token = getToken()
        const url = getAttachmentDownloadUrl(attachmentId, shareToken)

        const response = await fetch(url, {
          headers: {
            ...(!shareToken && token && { Authorization: `Bearer ${token}` }),
          },
        })

        if (!response.ok) {
          if (response.status === 403) {
            throw new Error('分享链接已过期或无效')
          }
          if (response.status === 404) {
            throw new Error('附件不存在或已被删除')
          }
          throw new Error('加载失败')
        }

        const fetchedBlob = await response.blob()

        if (isMounted) {
          setBlob(fetchedBlob)
          const url = URL.createObjectURL(fetchedBlob)
          currentBlobUrl = url
          setBlobUrl(url)
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : '加载失败')
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    fetchBlob()

    return () => {
      isMounted = false
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl)
      }
    }
  }, [attachmentId, externalBlob, shareToken, retryKey])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (blobUrl && blobUrl.startsWith('blob:')) {
        URL.revokeObjectURL(blobUrl)
      }
    }
  }, [blobUrl])

  return { blob, blobUrl, isLoading, error, refetch }
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/hooks/useFileBlob.ts
git commit -m "feat: add useFileBlob hook for fetching file blobs"
```

---

## Task 4: Create Preview Renderers

### Task 4.1: Image Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/ImagePreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useState, useCallback, useEffect } from 'react'
import { ZoomIn, ZoomOut, RotateCw, Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ImagePreviewProps {
  url: string
  filename: string
  onDownload?: () => void
  onClose?: () => void
  showToolbar?: boolean
}

export function ImagePreview({
  url,
  filename,
  onDownload,
  onClose,
  showToolbar = true,
}: ImagePreviewProps) {
  const [scale, setScale] = useState(1)
  const [rotation, setRotation] = useState(0)

  const handleZoomIn = useCallback(() => {
    setScale(s => Math.min(3, s + 0.1))
  }, [])

  const handleZoomOut = useCallback(() => {
    setScale(s => Math.max(0.1, s - 0.1))
  }, [])

  const handleRotate = useCallback(() => {
    setRotation(r => (r + 90) % 360)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case '+':
        case '=':
          handleZoomIn()
          break
        case '-':
          handleZoomOut()
          break
        case 'r':
        case 'R':
          handleRotate()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleZoomIn, handleZoomOut, handleRotate])

  return (
    <div className="flex flex-col h-full">
      {showToolbar && (
        <div className="flex items-center justify-center gap-2 p-2 bg-surface dark:bg-gray-800 border-b border-border dark:border-gray-700">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomOut}
            title="缩小 (-)"
          >
            <ZoomOut className="w-4 h-4" />
          </Button>
          <span className="text-sm text-text-secondary min-w-[60px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomIn}
            title="放大 (+)"
          >
            <ZoomIn className="w-4 h-4" />
          </Button>
          <div className="w-px h-6 bg-border dark:bg-gray-600 mx-2" />
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRotate}
            title="旋转 (R)"
          >
            <RotateCw className="w-4 h-4" />
          </Button>
          {onDownload && (
            <>
              <div className="w-px h-6 bg-border dark:bg-gray-600 mx-2" />
              <Button variant="ghost" size="sm" onClick={onDownload} title="下载">
                <Download className="w-4 h-4" />
              </Button>
            </>
          )}
          {onClose && (
            <>
              <div className="w-px h-6 bg-border dark:bg-gray-600 mx-2" />
              <Button variant="ghost" size="sm" onClick={onClose} title="关闭 (Esc)">
                <X className="w-4 h-4" />
              </Button>
            </>
          )}
        </div>
      )}

      <div className="flex-1 overflow-auto bg-gray-100 dark:bg-gray-900 flex items-center justify-center p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={url}
          alt={filename}
          className="max-w-full max-h-full object-contain transition-transform duration-200"
          style={{
            transform: `scale(${scale}) rotate(${rotation}deg)`,
          }}
        />
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/ImagePreview.tsx
git commit -m "feat: add ImagePreview renderer component"
```

### Task 4.2: PDF Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/PDFPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'

interface PDFPreviewProps {
  url: string
  filename: string
}

export function PDFPreview({ url, filename }: PDFPreviewProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 bg-gray-100 dark:bg-gray-900">
        <iframe src={url} className="w-full h-full border-0" title={filename} />
      </div>
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/PDFPreview.tsx
git commit -m "feat: add PDFPreview renderer component"
```

### Task 4.3: Text Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/TextPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'
import { isCodeFile } from '../utils'

interface TextPreviewProps {
  content: string
  filename: string
}

export function TextPreview({ content, filename }: TextPreviewProps) {
  const isCode = isCodeFile(filename)

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900">
      <div className="flex-1 overflow-auto p-4">
        {isCode ? (
          <pre className="font-mono text-sm text-text-primary dark:text-gray-200 whitespace-pre-wrap break-all">
            {content}
          </pre>
        ) : (
          <div className="text-text-primary dark:text-gray-200 whitespace-pre-wrap break-all leading-relaxed">
            {content}
          </div>
        )}
      </div>
    </div>
  )
}
```

**Step 4: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/TextPreview.tsx
git commit -m "feat: add TextPreview renderer component"
```

### Task 4.4: Video Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/VideoPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'

interface VideoPreviewProps {
  url: string
}

export function VideoPreview({ url }: VideoPreviewProps) {
  return (
    <div className="flex flex-col h-full bg-black">
      <div className="flex-1 flex items-center justify-center">
        <video src={url} controls className="max-w-full max-h-full" controlsList="nodownload">
          您的浏览器不支持视频播放
        </video>
      </div>
    </div>
  )
}
```

**Step 5: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/VideoPreview.tsx
git commit -m "feat: add VideoPreview renderer component"
```

### Task 4.5: Audio Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/AudioPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'
import { Music } from 'lucide-react'

interface AudioPreviewProps {
  url: string
  filename: string
}

export function AudioPreview({ url, filename }: AudioPreviewProps) {
  return (
    <div className="flex flex-col h-full bg-surface items-center justify-center p-8">
      <Music className="w-24 h-24 text-primary/50 mb-6" />
      <h3 className="text-lg font-medium mb-4 text-center break-all">{filename}</h3>
      <audio src={url} controls className="w-full max-w-md" controlsList="nodownload">
        您的浏览器不支持音频播放
      </audio>
    </div>
  )
}
```

**Step 6: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/AudioPreview.tsx
git commit -m "feat: add AudioPreview renderer component"
```

### Task 4.6: Excel Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/ExcelPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useState } from 'react'
import type { ExcelSheet } from '../hooks/useExcelParser'

interface ExcelPreviewProps {
  sheets: ExcelSheet[]
  filename: string
}

export function ExcelPreview({ sheets, filename }: ExcelPreviewProps) {
  const [activeSheet, setActiveSheet] = useState(0)

  if (sheets.length === 0) {
    return (
      <div className="flex flex-col h-full bg-white dark:bg-gray-900 items-center justify-center">
        <div className="text-text-secondary">无法解析表格内容</div>
      </div>
    )
  }

  const currentSheet = sheets[activeSheet]

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900">
      {/* Sheet tabs */}
      {sheets.length > 1 && (
        <div className="flex items-center gap-1 p-2 bg-surface dark:bg-gray-800 border-b border-border dark:border-gray-700 overflow-x-auto">
          {sheets.map((sheet, index) => (
            <button
              key={index}
              onClick={() => setActiveSheet(index)}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors whitespace-nowrap ${
                index === activeSheet
                  ? 'bg-white dark:bg-gray-700 text-text-primary dark:text-white shadow-sm border border-border dark:border-gray-600'
                  : 'text-text-secondary hover:text-text-primary hover:bg-white/50 dark:hover:bg-gray-700/50'
              }`}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      )}

      {/* Table content */}
      <div className="flex-1 overflow-auto">
        <div className="inline-block min-w-full">
          <table className="border-collapse text-sm">
            <tbody>
              {currentSheet.data.map((row, rowIndex) => (
                <tr key={rowIndex} className={rowIndex === 0 ? 'bg-surface dark:bg-gray-800' : ''}>
                  {/* Row number */}
                  <td className="sticky left-0 w-12 px-2 py-2 text-right text-xs text-text-secondary bg-inherit dark:bg-gray-800 border-r border-b border-border dark:border-gray-700 select-none">
                    {rowIndex + 1}
                  </td>
                  {row.map((cell, cellIndex) => {
                    const isHeader = rowIndex === 0
                    const cellValue = cell !== null && cell !== undefined ? String(cell) : ''

                    return (
                      <td
                        key={cellIndex}
                        className={`px-3 py-2 border-r border-b border-border dark:border-gray-700 min-w-[80px] max-w-[400px] ${
                          isHeader
                            ? 'font-semibold text-text-primary dark:text-white bg-surface dark:bg-gray-800'
                            : 'text-text-primary dark:text-gray-200 bg-white dark:bg-gray-900'
                        }`}
                        title={cellValue}
                      >
                        <div className="truncate">{cellValue}</div>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-surface dark:bg-gray-800 border-t border-border dark:border-gray-700 text-xs text-text-secondary">
        {filename} · {currentSheet.name} · {currentSheet.data.length} 行
      </div>
    </div>
  )
}
```

**Step 7: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/ExcelPreview.tsx
git commit -m "feat: add ExcelPreview renderer component"
```

### Task 4.7: Word Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/WordPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'

interface WordPreviewProps {
  content: string
  filename?: string
}

export function WordPreview({ content }: WordPreviewProps) {
  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900">
      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-3xl mx-auto">
          <div className="text-text-primary dark:text-gray-200 whitespace-pre-wrap break-all leading-relaxed">
            {content}
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 8: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/WordPreview.tsx
git commit -m "feat: add WordPreview renderer component"
```

### Task 4.8: Unknown Preview Renderer

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/UnknownPreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'
import { FileIcon } from 'lucide-react'
import { formatFileSize } from '../utils'

interface UnknownPreviewProps {
  filename: string
  fileSize?: number
}

export function UnknownPreview({ filename, fileSize }: UnknownPreviewProps) {
  return (
    <div className="flex flex-col h-full bg-surface items-center justify-center p-8">
      <FileIcon className="w-24 h-24 text-primary/50 mb-6" />
      <h3 className="text-lg font-medium mb-2 text-center break-all">{filename}</h3>
      {fileSize && <p className="text-sm text-text-secondary mb-6">{formatFileSize(fileSize)}</p>}
      <p className="text-text-secondary text-sm">该文件类型暂不支持预览，请下载查看</p>
    </div>
  )
}
```

**Step 9: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/UnknownPreview.tsx
git commit -m "feat: add UnknownPreview renderer component"
```

### Task 4.9: Create Renderers Index

**Files:**
- Create: `frontend/src/components/common/FilePreview/preview-renderers/index.ts`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

export { ImagePreview } from './ImagePreview'
export { PDFPreview } from './PDFPreview'
export { TextPreview } from './TextPreview'
export { VideoPreview } from './VideoPreview'
export { AudioPreview } from './AudioPreview'
export { ExcelPreview } from './ExcelPreview'
export { WordPreview } from './WordPreview'
export { UnknownPreview } from './UnknownPreview'
```

**Step 10: Commit**

```bash
git add frontend/src/components/common/FilePreview/preview-renderers/index.ts
git commit -m "feat: add preview renderers index export"
```

---

## Task 5: Create Hooks Index

**Files:**
- Create: `frontend/src/components/common/FilePreview/hooks/index.ts`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

export { useFileBlob } from './useFileBlob'
export { useExcelParser, type ExcelSheet } from './useExcelParser'
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/hooks/index.ts
git commit -m "feat: add hooks index export"
```

---

## Task 6: Create Main FilePreview Component

**Files:**
- Create: `frontend/src/components/common/FilePreview/FilePreview.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useEffect, useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import {
  ImagePreview,
  PDFPreview,
  TextPreview,
  VideoPreview,
  AudioPreview,
  ExcelPreview,
  WordPreview,
  UnknownPreview,
} from './preview-renderers'
import { useFileBlob, useExcelParser } from './hooks'
import { getPreviewType, getOfficeType, type PreviewType } from './utils'

export interface FilePreviewProps {
  /** Attachment ID for fetching file */
  attachmentId?: number
  /** Direct file blob (alternative to attachmentId) */
  fileBlob?: Blob
  /** Filename for display and type detection */
  filename: string
  /** MIME type for type detection */
  mimeType: string
  /** File size for display */
  fileSize?: number
  /** Optional share token for public access */
  shareToken?: string
  /** Callback when download is requested */
  onDownload?: () => void
  /** Callback when close is requested */
  onClose?: () => void
  /** Whether to show toolbar (for fullscreen mode) */
  showToolbar?: boolean
}

/**
 * FilePreview component - Renders preview for various file types
 * Supports: image, PDF, text, video, audio, Excel, Word/PPT
 */
export function FilePreview({
  attachmentId,
  fileBlob,
  filename,
  mimeType,
  fileSize,
  shareToken,
  onDownload,
  onClose,
  showToolbar = true,
}: FilePreviewProps) {
  const [textContent, setTextContent] = useState<string>('')
  const previewType = getPreviewType(mimeType, filename)

  const { blob, blobUrl, isLoading, error } = useFileBlob(
    attachmentId,
    fileBlob,
    shareToken
  )

  const { sheets, parseExcel } = useExcelParser()

  // Parse text and Excel content when blob is available
  useEffect(() => {
    if (!blob) return

    const parseContent = async () => {
      if (previewType === 'text') {
        try {
          const text = await blob.text()
          setTextContent(text)
        } catch (err) {
          console.error('Failed to read text content:', err)
        }
      } else if (previewType === 'office') {
        const officeType = getOfficeType(filename)
        if (officeType === 'excel') {
          await parseExcel(blob)
        } else {
          // Word/PPT - try to read as text
          try {
            const text = await blob.text()
            setTextContent(text)
          } catch (err) {
            console.error('Failed to read office content:', err)
          }
        }
      }
    }

    parseContent()
  }, [blob, previewType, filename, parseExcel])

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px]">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-2" />
        <p className="text-text-secondary text-sm">加载中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] p-4">
        <AlertCircle className="w-12 h-12 text-red-500 mb-2" />
        <p className="text-red-600 text-sm text-center">{error}</p>
      </div>
    )
  }

  // Render based on preview type
  switch (previewType) {
    case 'image':
      return blobUrl ? (
        <ImagePreview
          url={blobUrl}
          filename={filename}
          onDownload={onDownload}
          onClose={onClose}
          showToolbar={showToolbar}
        />
      ) : null

    case 'pdf':
      return blobUrl ? <PDFPreview url={blobUrl} filename={filename} /> : null

    case 'text':
      return <TextPreview content={textContent} filename={filename} />

    case 'video':
      return blobUrl ? <VideoPreview url={blobUrl} /> : null

    case 'audio':
      return blobUrl ? <AudioPreview url={blobUrl} filename={filename} /> : null

    case 'office': {
      const officeType = getOfficeType(filename)
      if (officeType === 'excel') {
        return <ExcelPreview sheets={sheets} filename={filename} />
      }
      return <WordPreview content={textContent} filename={filename} />
    }

    case 'unknown':
    default:
      return <UnknownPreview filename={filename} fileSize={fileSize} />
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/FilePreview.tsx
git commit -m "feat: add main FilePreview component"
```

---

## Task 7: Create FilePreviewDialog Component

**Files:**
- Create: `frontend/src/components/common/FilePreview/FilePreviewDialog.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useEffect } from 'react'
import { FileIcon, Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FilePreview } from './FilePreview'
import { getPreviewType, formatFileSize } from './utils'
import { downloadAttachment } from '@/apis/attachments'

export interface FilePreviewDialogProps {
  /** Whether dialog is open */
  open: boolean
  /** Callback when dialog is closed */
  onClose: () => void
  /** Attachment ID */
  attachmentId: number
  /** Filename */
  filename: string
  /** MIME type */
  mimeType: string
  /** File size */
  fileSize?: number
  /** Optional share token */
  shareToken?: string
}

/**
 * FilePreviewDialog - Dialog wrapper for FilePreview
 * Used in task pages for clicking to preview files
 */
export function FilePreviewDialog({
  open,
  onClose,
  attachmentId,
  filename,
  mimeType,
  fileSize,
  shareToken,
}: FilePreviewDialogProps) {
  const previewType = getPreviewType(mimeType, filename)

  // Handle keyboard shortcut (Escape to close)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  const handleDownload = async () => {
    try {
      await downloadAttachment(attachmentId, filename, shareToken)
    } catch (err) {
      console.error('Failed to download:', err)
    }
  }

  // Get file icon based on type
  const getFileIcon = () => {
    switch (previewType) {
      case 'image':
        return '🖼️'
      case 'pdf':
        return '📄'
      case 'video':
        return '🎬'
      case 'audio':
        return '🎵'
      case 'text':
        return '📃'
      case 'office':
        return '📊'
      default:
        return '📎'
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-5xl w-[90vw] h-[80vh] p-0 flex flex-col">
        <DialogHeader className="px-4 py-3 border-b border-border flex flex-row items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-2xl">{getFileIcon()}</span>
            <div className="min-w-0">
              <DialogTitle className="text-base font-medium truncate max-w-[300px] sm:max-w-[400px]">
                {filename}
              </DialogTitle>
              {fileSize && (
                <p className="text-xs text-text-secondary">
                  {formatFileSize(fileSize)}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button variant="outline" size="sm" onClick={handleDownload}>
              <Download className="w-4 h-4 mr-2" />
              下载
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="w-5 h-5" />
            </Button>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-hidden">
          <FilePreview
            attachmentId={attachmentId}
            filename={filename}
            mimeType={mimeType}
            fileSize={fileSize}
            shareToken={shareToken}
            onDownload={handleDownload}
            onClose={onClose}
            showToolbar={false} // Hide toolbar in dialog mode (we have header)
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/FilePreviewDialog.tsx
git commit -m "feat: add FilePreviewDialog component"
```

---

## Task 8: Create FilePreviewPage Component

**Files:**
- Create: `frontend/src/components/common/FilePreview/FilePreviewPage.tsx`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React from 'react'
import { FileIcon, Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { FilePreview } from './FilePreview'
import { getPreviewType, formatFileSize } from './utils'
import { downloadAttachment } from '@/apis/attachments'

export interface FilePreviewPageProps {
  /** Attachment ID */
  attachmentId?: number
  /** Direct file blob */
  fileBlob?: Blob
  /** Filename */
  filename: string
  /** MIME type */
  mimeType: string
  /** File size */
  fileSize?: number
  /** Optional share token */
  shareToken?: string
  /** Callback when close is requested */
  onClose?: () => void
}

/**
 * FilePreviewPage - Fullscreen page wrapper for FilePreview
 * Used in /download/shared page
 */
export function FilePreviewPage({
  attachmentId,
  fileBlob,
  filename,
  mimeType,
  fileSize,
  shareToken,
  onClose,
}: FilePreviewPageProps) {
  const previewType = getPreviewType(mimeType, filename)

  const handleDownload = async () => {
    if (attachmentId) {
      try {
        await downloadAttachment(attachmentId, filename, shareToken)
      } catch (err) {
        console.error('Failed to download:', err)
      }
    } else if (fileBlob) {
      // Download from blob
      const url = URL.createObjectURL(fileBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }

  // Get file icon
  const getFileIcon = () => {
    switch (previewType) {
      case 'image':
        return '🖼️'
      case 'pdf':
        return '📄'
      case 'video':
        return '🎬'
      case 'audio':
        return '🎵'
      case 'text':
        return '📃'
      case 'office':
        return '📊'
      default:
        return '📎'
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border dark:border-gray-700 bg-white dark:bg-gray-900 sticky top-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-2xl">{getFileIcon()}</span>
          <div className="min-w-0">
            <h1 className="font-medium text-text-primary truncate max-w-[200px] sm:max-w-[300px] md:max-w-[500px]">
              {filename}
            </h1>
            {fileSize && (
              <p className="text-xs text-text-secondary">
                {formatFileSize(fileSize)}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Button variant="primary" size="sm" onClick={handleDownload}>
            <Download className="w-4 h-4 mr-2" />
            下载
          </Button>
          {onClose && (
            <Button variant="ghost" size="icon" onClick={onClose} title="关闭">
              <X className="w-5 h-5" />
            </Button>
          )}
        </div>
      </header>

      {/* Preview Area */}
      <main className="flex-1 overflow-hidden">
        <FilePreview
          attachmentId={attachmentId}
          fileBlob={fileBlob}
          filename={filename}
          mimeType={mimeType}
          fileSize={fileSize}
          shareToken={shareToken}
          onDownload={handleDownload}
          onClose={onClose}
          showToolbar={true}
        />
      </main>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/FilePreviewPage.tsx
git commit -m "feat: add FilePreviewPage component"
```

---

## Task 9: Create Main Index Export

**Files:**
- Create: `frontend/src/components/common/FilePreview/index.ts`

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

export { FilePreview, type FilePreviewProps } from './FilePreview'
export { FilePreviewDialog, type FilePreviewDialogProps } from './FilePreviewDialog'
export { FilePreviewPage, type FilePreviewPageProps } from './FilePreviewPage'
export {
  getPreviewType,
  formatFileSize,
  getOfficeType,
  isCodeFile,
  type PreviewType,
} from './utils'
export { useFileBlob, useExcelParser, type ExcelSheet } from './hooks'
export {
  ImagePreview,
  PDFPreview,
  TextPreview,
  VideoPreview,
  AudioPreview,
  ExcelPreview,
  WordPreview,
  UnknownPreview,
} from './preview-renderers'
```

**Step 2: Commit**

```bash
git add frontend/src/components/common/FilePreview/index.ts
git commit -m "feat: add FilePreview module index export"
```

---

## Task 10: Refactor /download/shared Page

**Files:**
- Modify: `frontend/src/app/download/shared/page.tsx`

**Step 1: Replace entire file content**

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { UserProvider, useUser } from '@/features/common/UserContext'
import { getToken } from '@/apis/user'
import { FilePreviewPage } from '@/components/common/FilePreview'

const API_BASE_URL = ''

interface AttachmentInfo {
  id: number
  filename: string
  mime_type: string
  file_size?: number
  fileData?: Blob
}

// Inner component that uses useSearchParams
function PublicDownloadContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const { user, isLoading: authLoading } = useUser()
  const [attachmentInfo, setAttachmentInfo] = useState<AttachmentInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const token = searchParams.get('token')
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

    if (!token) {
      setError('无效的分享链接')
      setLoading(false)
      return
    }

    // Logged in, fetch file for preview
    fetchFileForPreview()

    // Cleanup
    return () => {
      // Blob URLs are managed by FilePreview component
    }
  }, [isAuthenticated, authLoading, token])

  const fetchFileForPreview = async () => {
    try {
      setLoading(true)
      const authToken = getToken()

      // Fetch the file from backend
      const response = await fetch(
        `${API_BASE_URL}/api/attachments/download/shared?token=${encodeURIComponent(token!)}`,
        {
          headers: {
            ...(authToken && { Authorization: `Bearer ${authToken}` }),
          },
        }
      )

      if (!response.ok) {
        if (response.status === 403) {
          throw new Error('分享链接已过期或无效')
        }
        if (response.status === 404) {
          throw new Error('附件不存在或已被删除')
        }
        throw new Error('加载失败')
      }

      // Get filename from Content-Disposition header
      const contentDisposition = response.headers.get('Content-Disposition')
      let filename = 'download'
      if (contentDisposition) {
        const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;"]+)/)
        if (encodedMatch) {
          filename = decodeURIComponent(encodedMatch[1])
        } else {
          const simpleMatch = contentDisposition.match(/filename="([^"]+)"|filename=([^;]+)/)
          if (simpleMatch) {
            filename = simpleMatch[1] || simpleMatch[2]?.trim() || filename
          }
        }
      }

      const contentType = response.headers.get('Content-Type') || 'application/octet-stream'
      const contentLength = response.headers.get('Content-Length')

      const blob = await response.blob()

      setAttachmentInfo({
        id: 0,
        filename,
        mime_type: contentType,
        file_size: contentLength ? parseInt(contentLength) : blob.size,
        fileData: blob,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    router.push('/chat')
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-gray-600 dark:text-gray-400">加载中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 mx-auto text-red-500 mb-4" />
          <h1 className="text-xl font-semibold mb-2 dark:text-white">加载失败</h1>
          <p className="text-gray-600 dark:text-gray-400 mb-6">{error}</p>
          <Button onClick={() => router.push('/chat')}>返回首页</Button>
        </div>
      </div>
    )
  }

  if (!attachmentInfo) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 mx-auto text-yellow-500 mb-4" />
          <h1 className="text-xl font-semibold mb-2 dark:text-white">无法加载文件</h1>
          <Button onClick={() => router.push('/chat')}>返回首页</Button>
        </div>
      </div>
    )
  }

  return (
    <FilePreviewPage
      fileBlob={attachmentInfo.fileData}
      filename={attachmentInfo.filename}
      mimeType={attachmentInfo.mime_type}
      fileSize={attachmentInfo.file_size}
      onClose={handleClose}
    />
  )
}

// Main export with UserProvider wrapper and Suspense
export default function PublicAttachmentDownloadPage() {
  return (
    <UserProvider>
      <Suspense
        fallback={
          <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-gray-600 dark:text-gray-400">加载中...</p>
            </div>
          </div>
        }
      >
        <PublicDownloadContent />
      </Suspense>
    </UserProvider>
  )
}
```

**Step 2: Verify the page works**

Run: `cd frontend && npm run build 2>&1 | head -50`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/src/app/download/shared/page.tsx
git commit -m "refactor: use FilePreviewPage component in /download/shared"
```

---

## Task 11: Update AttachmentCard to Support Preview

**Files:**
- Modify: `frontend/src/components/common/AttachmentCard.tsx`

**Step 1: Add preview functionality**

Replace the file content with:

```typescript
// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import React, { useEffect, useState } from 'react'
import { Download, Loader2, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { downloadAttachment, getAttachment, getFileIcon } from '@/apis/attachments'
import type { AttachmentDetailResponse } from '@/apis/attachments'
import { useShareToken } from '@/contexts/ShareTokenContext'
import { FilePreviewDialog } from '@/components/common/FilePreview'

// Global cache for attachment details to avoid redundant API calls
const attachmentCache = new Map<number, AttachmentDetailResponse>()

interface AttachmentCardProps {
  /** Attachment ID */
  attachmentId: number
}

/**
 * AttachmentCard component displays a file attachment as a card with preview and download options
 *
 * Features:
 * - Fetches attachment details from API (with caching)
 * - File icon based on extension
 * - Filename and type label
 * - Preview button (opens dialog)
 * - Download button (downloads with authentication)
 */
export function AttachmentCard({ attachmentId }: AttachmentCardProps) {
  const { shareToken } = useShareToken()
  const [attachment, setAttachment] = useState<AttachmentDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)

  // Fetch attachment details on mount (with caching)
  useEffect(() => {
    const fetchAttachment = async () => {
      try {
        setLoading(true)

        // Check cache first
        const cached = attachmentCache.get(attachmentId)
        if (cached) {
          setAttachment(cached)
          setLoading(false)
          return
        }

        // Fetch from API if not cached
        const data = await getAttachment(attachmentId, shareToken)
        attachmentCache.set(attachmentId, data) // Cache the result
        setAttachment(data)
      } catch (err) {
        console.error('Failed to fetch attachment:', err)
        setError(err instanceof Error ? err.message : 'Failed to load attachment')
      } finally {
        setLoading(false)
      }
    }

    fetchAttachment()
  }, [attachmentId, shareToken])

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await downloadAttachment(attachmentId, attachment?.filename, shareToken)
    } catch (error) {
      console.error('Failed to download attachment:', error)
    }
  }

  const handlePreview = () => {
    setPreviewOpen(true)
  }

  const handleClosePreview = () => {
    setPreviewOpen(false)
  }

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center gap-4 p-4 rounded-xl border border-border bg-surface">
        <div className="flex-shrink-0 w-16 h-16 flex items-center justify-center bg-base rounded-lg border border-border">
          <Loader2 className="h-6 w-6 animate-spin text-text-muted" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="h-5 bg-border rounded animate-pulse mb-2 w-3/4" />
          <div className="h-4 bg-border rounded animate-pulse w-1/2" />
        </div>
      </div>
    )
  }

  // Error state
  if (error || !attachment) {
    return (
      <div className="flex items-center gap-4 p-4 rounded-xl border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/20">
        <div className="flex-shrink-0 w-16 h-16 flex items-center justify-center bg-base rounded-lg border border-border">
          <span className="text-3xl">⚠️</span>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-medium text-red-800 dark:text-red-200">
            Failed to load attachment
          </h3>
          <p className="text-sm text-red-600 dark:text-red-400">{error || 'Unknown error'}</p>
        </div>
      </div>
    )
  }

  // Get file icon emoji
  const fileIcon = getFileIcon(attachment.file_extension)

  // Get file type label
  const fileTypeLabel = getFileTypeLabel(attachment.file_extension)

  // Check if file is previewable
  const isPreviewable = isFilePreviewable(attachment.mime_type, attachment.file_extension)

  return (
    <>
      <div
        className="flex items-center gap-4 p-4 rounded-xl border border-border bg-surface hover:bg-surface-hover transition-colors cursor-pointer"
        onClick={isPreviewable ? handlePreview : undefined}
      >
        {/* File Icon */}
        <div className="flex-shrink-0 w-16 h-16 flex items-center justify-center bg-base rounded-lg border border-border">
          <span className="text-3xl">{fileIcon}</span>
        </div>

        {/* File Info */}
        <div className="flex-1 min-w-0">
          <h3
            className="text-base font-medium text-text-primary truncate"
            title={attachment.filename}
          >
            {attachment.filename}
          </h3>
          <p className="text-sm text-text-secondary">
            {fileTypeLabel} · {attachment.file_extension.replace('.', '').toUpperCase()}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Preview Button */}
          {isPreviewable && (
            <Button
              variant="ghost"
              size="icon"
              onClick={e => {
                e.stopPropagation()
                handlePreview()
              }}
              className="h-10 w-10 rounded-lg hover:bg-primary/10"
              title="预览"
            >
              <Eye className="h-5 w-5 text-text-secondary" />
            </Button>
          )}

          {/* Download Button */}
          <Button
            variant="outline"
            onClick={handleDownload}
            className="h-10 px-4 rounded-lg hover:bg-primary/10"
          >
            <Download className="h-4 w-4 mr-2" />
            Download
          </Button>
        </div>
      </div>

      {/* Preview Dialog */}
      {isPreviewable && (
        <FilePreviewDialog
          open={previewOpen}
          onClose={handleClosePreview}
          attachmentId={attachmentId}
          filename={attachment.filename}
          mimeType={attachment.mime_type}
          fileSize={attachment.file_size}
          shareToken={shareToken}
        />
      )}
    </>
  )
}

/**
 * Check if file type is previewable
 */
function isFilePreviewable(mimeType: string, extension: string): boolean {
  // Image types
  if (mimeType.startsWith('image/')) return true
  // PDF
  if (mimeType === 'application/pdf') return true
  // Video
  if (mimeType.startsWith('video/')) return true
  // Audio
  if (mimeType.startsWith('audio/')) return true
  // Text files
  if (
    mimeType.startsWith('text/') ||
    mimeType === 'application/json' ||
    mimeType === 'application/javascript' ||
    mimeType === 'application/xml' ||
    extension.match(/\.(txt|md|json|js|ts|jsx|tsx|py|java|go|rs|cpp|c|h|hpp|css|scss|less|html|htm|xml|yaml|yml|sh|bash|zsh|ps1|sql|log)$/i)
  ) {
    return true
  }
  // Office documents
  if (
    mimeType.includes('officedocument') ||
    mimeType.includes('msword') ||
    mimeType.includes('ms-excel') ||
    mimeType.includes('ms-powerpoint') ||
    mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  ) {
    return true
  }
  return false
}

/**
 * Get file type label based on extension
 */
function getFileTypeLabel(extension: string): string {
  const ext = extension.toLowerCase().replace('.', '')

  // Document types
  if (['pdf'].includes(ext)) return 'Document'
  if (['doc', 'docx'].includes(ext)) return 'Word Document'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'Spreadsheet'
  if (['ppt', 'pptx'].includes(ext)) return 'Presentation'
  if (['txt', 'md'].includes(ext)) return 'Text'

  // Image types
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext)) return 'Image'

  // Code types
  if (['js', 'ts', 'jsx', 'tsx', 'py', 'java', 'go', 'rs', 'cpp', 'c'].includes(ext)) return 'Code'

  // Config types
  if (['json', 'yaml', 'yml', 'xml', 'toml'].includes(ext)) return 'Configuration'

  // Default
  return 'File'
}

export default AttachmentCard
```

**Step 2: Verify build**

Run: `cd frontend && npm run build 2>&1 | grep -i "error\\|failed" | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/common/AttachmentCard.tsx
git commit -m "feat: add preview support to AttachmentCard using FilePreviewDialog"
```

---

## Task 12: Run Frontend Build Verification

**Step 1: Build the frontend**

Run: `cd frontend && npm run build 2>&1 | tail -30`
Expected: Build completes successfully

**Step 2: Check for TypeScript errors**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No TypeScript errors

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete file preview reuse implementation

- Extract file preview functionality into reusable components
- Create FilePreview, FilePreviewDialog, and FilePreviewPage components
- Support image, PDF, text, video, audio, Excel, Word/PPT previews
- Refactor /download/shared page to use FilePreviewPage
- Update AttachmentCard with preview dialog support"
```

---

## Summary

This implementation plan creates a modular file preview system that:

1. **Extracts** preview functionality from `/download/shared/page.tsx` into reusable components
2. **Supports** multiple file types: image, PDF, text, video, audio, Excel, Word/PPT
3. **Provides** three usage modes:
   - `FilePreview` - Base component for embedding
   - `FilePreviewDialog` - Dialog wrapper for task pages
   - `FilePreviewPage` - Fullscreen page for shared downloads
4. **Integrates** with existing `AttachmentCard` component for preview on click
5. **Maintains** all existing functionality including Excel parsing with SheetJS

All components are located in `frontend/src/components/common/FilePreview/` with proper TypeScript types and exports.
