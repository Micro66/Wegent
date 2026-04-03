// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from 'react'
import { Building2, Clock3, Database, Loader2, Plus, User, Users, XIcon } from 'lucide-react'
import type { TFunction } from 'i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { formatDocumentCount } from '@/lib/i18n-helpers'
import { useTranslation } from '@/hooks/useTranslation'
import type { KnowledgeBaseDefaultRef } from '@/types/api'
import {
  KnowledgeBaseOption,
  KnowledgeBaseOptionSource,
  useKnowledgeBaseOptions,
} from '../../hooks/useKnowledgeBaseOptions'

interface KnowledgeBaseMultiSelectorProps {
  value: KnowledgeBaseDefaultRef[]
  onChange: (value: KnowledgeBaseDefaultRef[]) => void
  disabled?: boolean
}

const SELECTED_SECTION_HEIGHT = 'h-[180px]'
const AVAILABLE_SECTION_HEIGHT = 'h-[320px]'

function formatUpdatedAt(value: string): string {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')

  return `${year}-${month}-${day} ${hours}:${minutes}`
}

function matchesSearch(option: KnowledgeBaseOption, search: string): boolean {
  const normalizedSearch = search.trim().toLowerCase()
  if (!normalizedSearch) {
    return true
  }

  return [option.name, option.description || '', option.groupName, option.namespace]
    .join(' ')
    .toLowerCase()
    .includes(normalizedSearch)
}

function getSourceIcon(source: KnowledgeBaseOptionSource) {
  switch (source) {
    case 'personal':
      return User
    case 'group':
      return Users
    case 'organization':
      return Building2
  }
}

function getSourceLabel(source: KnowledgeBaseOptionSource, t: TFunction) {
  switch (source) {
    case 'personal':
      return t('common:bot.default_knowledge_bases_source_personal', '个人')
    case 'group':
      return t('common:bot.default_knowledge_bases_source_group', '群组')
    case 'organization':
      return t('common:bot.default_knowledge_bases_source_organization', '组织')
  }
}

function getGroupTitle(source: KnowledgeBaseOptionSource, t: TFunction) {
  switch (source) {
    case 'personal':
      return t('common:bot.default_knowledge_bases_group_personal', '个人知识库')
    case 'group':
      return t('common:bot.default_knowledge_bases_group_group', '群组知识库')
    case 'organization':
      return t('common:bot.default_knowledge_bases_group_organization', '组织知识库')
  }
}

function buildFallbackOption(item: KnowledgeBaseDefaultRef): KnowledgeBaseOption {
  return {
    id: item.id,
    name: item.name,
    description: null,
    namespace: 'default',
    documentCount: 0,
    updatedAt: '',
    groupName: 'Personal',
    source: 'personal',
    isShared: false,
  }
}

interface KnowledgeBaseCardProps {
  item: KnowledgeBaseOption
  selected: boolean
  disabled: boolean
  onAdd: (item: KnowledgeBaseOption) => void
  onRemove: (knowledgeBaseId: number) => void
  t: TFunction
}

function KnowledgeBaseCard({
  item,
  selected,
  disabled,
  onAdd,
  onRemove,
  t,
}: KnowledgeBaseCardProps) {
  const SourceIcon = getSourceIcon(item.source)
  const updatedAt = formatUpdatedAt(item.updatedAt)
  const documentText = formatDocumentCount(item.documentCount || 0, t)

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-base p-3 transition-colors',
        selected ? 'border-primary/30 bg-primary/5' : 'hover:bg-surface/60'
      )}
      data-testid={selected ? `default-knowledge-base-chip-${item.id}` : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Database className="h-4 w-4" />
            </div>

            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium text-text-primary">{item.name}</span>
                <Badge variant="info" size="sm" className="gap-1">
                  <SourceIcon className="h-3 w-3" />
                  {getSourceLabel(item.source, t)}
                </Badge>
                {item.source === 'group' && item.groupName ? (
                  <Badge variant="secondary" size="sm">
                    {item.groupName}
                  </Badge>
                ) : null}
                {item.isShared ? (
                  <Badge variant="secondary" size="sm">
                    {t('common:bot.default_knowledge_bases_source_shared', '共享')}
                  </Badge>
                ) : null}
                <Badge variant="secondary" size="sm">
                  {documentText}
                </Badge>
                {selected ? (
                  <Badge variant="info" size="sm">
                    {t('common:bot.default_knowledge_bases_selected_badge', '已选')}
                  </Badge>
                ) : null}
              </div>

              {item.description ? (
                <p className="line-clamp-1 text-xs text-text-secondary">{item.description}</p>
              ) : null}

              {updatedAt ? (
                <div className="flex items-center gap-1 text-xs text-text-muted">
                  <Clock3 className="h-3 w-3" />
                  <span>
                    {`${t('common:bot.default_knowledge_bases_updated_at', '最近更新')} ${updatedAt}`}
                  </span>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {selected ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            className="h-8 px-2 text-text-muted hover:text-text-primary"
            onClick={() => onRemove(item.id)}
            data-testid={`default-knowledge-base-remove-${item.id}`}
          >
            <XIcon className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            className="h-8 px-2"
            onClick={() => onAdd(item)}
            data-testid={`default-knowledge-base-option-${item.id}`}
          >
            <Plus className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

export function KnowledgeBaseMultiSelector({
  value,
  onChange,
  disabled = false,
}: KnowledgeBaseMultiSelectorProps) {
  const { t } = useTranslation()
  const { options, loading, error } = useKnowledgeBaseOptions()
  const [search, setSearch] = useState('')

  const selectedIds = useMemo(() => new Set(value.map(item => item.id)), [value])
  const optionsById = useMemo(() => new Map(options.map(option => [option.id, option])), [options])

  const selectedItems = useMemo(
    () =>
      value
        .map(item => optionsById.get(item.id) ?? buildFallbackOption(item))
        .filter(item => matchesSearch(item, search)),
    [optionsById, search, value]
  )

  const availableItems = useMemo(
    () => options.filter(option => !selectedIds.has(option.id) && matchesSearch(option, search)),
    [options, search, selectedIds]
  )

  const groupedAvailableItems = useMemo(
    () => ({
      personal: availableItems.filter(item => item.source === 'personal'),
      group: availableItems.filter(item => item.source === 'group'),
      organization: availableItems.filter(item => item.source === 'organization'),
    }),
    [availableItems]
  )

  const handleSelect = (option: KnowledgeBaseOption) => {
    onChange([...value, { id: option.id, name: option.name }])
    setSearch('')
  }

  const handleRemove = (knowledgeBaseId: number) => {
    onChange(value.filter(item => item.id !== knowledgeBaseId))
  }

  return (
    <div
      className="space-y-4 rounded-lg border border-border bg-base p-4"
      data-testid="default-knowledge-base-selector"
    >
      <div className="space-y-2">
        <Input
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder={t('common:bot.default_knowledge_bases_search_placeholder', '搜索知识库')}
          disabled={disabled || loading}
          data-testid="default-knowledge-base-search-input"
        />
        <p className="text-xs text-text-muted">
          {t(
            'common:bot.default_knowledge_bases_used_for_new_chats',
            '用于初始化新聊天的默认知识库。'
          )}
        </p>
        <p className="text-xs text-text-muted">
          {t(
            'common:bot.default_knowledge_bases_append_hint',
            '聊天时手动选择的知识库会在后续追加，不会覆盖这里的默认配置。'
          )}
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-text-primary">
            {t('common:bot.default_knowledge_bases_selected_section', '已选默认知识库')}
          </h4>
          <Badge variant="secondary" size="sm">
            {t('common:bot.default_knowledge_bases_selected_count', {
              count: value.length,
              defaultValue: `已选 ${value.length} 个`,
            })}
          </Badge>
        </div>

        <div
          className={cn(
            SELECTED_SECTION_HEIGHT,
            'overflow-y-auto rounded-lg border border-border bg-surface/40 p-3'
          )}
          data-testid="default-knowledge-base-selected-section"
        >
          {selectedItems.length > 0 ? (
            <div className="space-y-3">
              {selectedItems.map(item => (
                <KnowledgeBaseCard
                  key={item.id}
                  item={item}
                  selected={true}
                  disabled={disabled}
                  onAdd={handleSelect}
                  onRemove={handleRemove}
                  t={t}
                />
              ))}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-base/70 px-4 text-center text-sm text-text-muted">
              {t('common:bot.default_knowledge_bases_empty_selection', '尚未选择默认知识库')}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-text-primary">
            {t('common:bot.default_knowledge_bases_available_section', '可添加知识库')}
          </h4>
        </div>

        <div
          className={cn(
            AVAILABLE_SECTION_HEIGHT,
            'overflow-y-auto rounded-lg border border-border bg-surface/40 p-3'
          )}
          data-testid="default-knowledge-base-available-section"
        >
          {loading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-text-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t('common:bot.default_knowledge_bases_loading', '知识库加载中...')}</span>
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-base/70 px-4 text-center text-sm text-text-muted">
              {t('common:bot.default_knowledge_bases_load_failed', '知识库加载失败')}
            </div>
          ) : availableItems.length === 0 ? (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border bg-base/70 px-4 text-center text-sm text-text-muted">
              {search
                ? t('common:bot.default_knowledge_bases_no_match', '没有匹配的知识库')
                : t('common:bot.default_knowledge_bases_no_options', '暂无可用知识库')}
            </div>
          ) : (
            <div className="space-y-4">
              {(['personal', 'group', 'organization'] as KnowledgeBaseOptionSource[]).map(
                source => {
                  const items = groupedAvailableItems[source]
                  if (items.length === 0) {
                    return null
                  }

                  return (
                    <section
                      key={source}
                      className="space-y-3"
                      data-testid={`default-knowledge-base-group-${source}`}
                    >
                      <div className="sticky top-0 z-10 -mx-3 border-y border-border bg-surface/95 px-3 py-2 backdrop-blur">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium uppercase tracking-[0.08em] text-text-secondary">
                            {getGroupTitle(source, t)}
                          </span>
                          <Badge variant="secondary" size="sm">
                            {items.length}
                          </Badge>
                        </div>
                      </div>

                      <div className="space-y-3">
                        {items.map(item => (
                          <KnowledgeBaseCard
                            key={item.id}
                            item={item}
                            selected={false}
                            disabled={disabled}
                            onAdd={handleSelect}
                            onRemove={handleRemove}
                            t={t}
                          />
                        ))}
                      </div>
                    </section>
                  )
                }
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
