// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from 'react'
import { Loader2, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useTranslation } from '@/hooks/useTranslation'
import type { KnowledgeBaseDefaultRef } from '@/types/api'
import { useKnowledgeBaseOptions } from '../../hooks/useKnowledgeBaseOptions'

interface KnowledgeBaseMultiSelectorProps {
  value: KnowledgeBaseDefaultRef[]
  onChange: (value: KnowledgeBaseDefaultRef[]) => void
  disabled?: boolean
}

export function KnowledgeBaseMultiSelector({
  value,
  onChange,
  disabled = false,
}: KnowledgeBaseMultiSelectorProps) {
  const { t } = useTranslation('common')
  const { options, loading, error } = useKnowledgeBaseOptions()
  const [search, setSearch] = useState('')

  const selectedIds = useMemo(() => new Set(value.map(item => item.id)), [value])

  const filteredOptions = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return options.filter(option => {
      if (selectedIds.has(option.id)) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      return option.name.toLowerCase().includes(normalizedSearch)
    })
  }, [options, search, selectedIds])

  const handleSelect = (option: KnowledgeBaseDefaultRef) => {
    onChange([...value, option])
    setSearch('')
  }

  const handleRemove = (knowledgeBaseId: number) => {
    onChange(value.filter(item => item.id !== knowledgeBaseId))
  }

  return (
    <div
      className="rounded-lg border border-border bg-base p-3 space-y-3"
      data-testid="default-knowledge-base-selector"
    >
      <div className="space-y-1">
        <Input
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder={t('bot.default_knowledge_bases_search_placeholder')}
          disabled={disabled || loading}
          data-testid="default-knowledge-base-search-input"
        />
        <p className="text-xs text-text-muted">
          {t('bot.default_knowledge_bases_used_for_new_chats')}
        </p>
        <p className="text-xs text-text-muted">{t('bot.default_knowledge_bases_append_hint')}</p>
      </div>

      {value.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {value.map(item => (
            <div
              key={item.id}
              className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-sm"
              data-testid={`default-knowledge-base-chip-${item.id}`}
            >
              <span>{item.name}</span>
              <button
                type="button"
                onClick={() => handleRemove(item.id)}
                disabled={disabled}
                className="text-text-muted hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50"
                data-testid={`default-knowledge-base-remove-${item.id}`}
              >
                <XIcon className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-text-muted">
          {t('bot.default_knowledge_bases_empty_selection')}
        </div>
      )}

      <div className="max-h-56 overflow-y-auto rounded-md border border-border bg-surface">
        {loading ? (
          <div className="flex items-center gap-2 px-3 py-4 text-sm text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t('bot.default_knowledge_bases_loading')}</span>
          </div>
        ) : error ? (
          <div className="px-3 py-4 text-sm text-text-muted">
            {t('bot.default_knowledge_bases_load_failed')}
          </div>
        ) : filteredOptions.length === 0 ? (
          <div className="px-3 py-4 text-sm text-text-muted">
            {search
              ? t('bot.default_knowledge_bases_no_match')
              : t('bot.default_knowledge_bases_no_options')}
          </div>
        ) : (
          <div className="flex flex-col">
            {filteredOptions.map(option => (
              <Button
                key={option.id}
                type="button"
                variant="ghost"
                className="justify-start rounded-none px-3 py-2 text-left"
                onClick={() => handleSelect(option)}
                disabled={disabled}
                data-testid={`default-knowledge-base-option-${option.id}`}
              >
                {option.name}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
