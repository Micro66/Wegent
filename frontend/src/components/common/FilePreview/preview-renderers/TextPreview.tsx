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
