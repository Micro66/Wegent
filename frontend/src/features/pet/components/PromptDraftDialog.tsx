// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { modelApis, type UnifiedModel } from '@/apis/models'
import { taskApis } from '@/apis/tasks'
import {
  clearPromptDraft,
  getPromptDraft,
  savePromptDraft,
} from '@/features/pet/utils/promptDraftStorage'
import { useTranslation } from '@/hooks/useTranslation'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SearchableSelect } from '@/components/ui/searchable-select'
import PromptFineTuneDialog from '@/features/settings/components/prompt-fine-tune/PromptFineTuneDialog'

interface PromptDraftDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number | null
}

export function PromptDraftDialog({ open, onOpenChange, taskId }: PromptDraftDialogProps) {
  const { t } = useTranslation('pet')
  const [models, setModels] = useState<UnifiedModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [model, setModel] = useState('')
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [openFineTune, setOpenFineTune] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const conversationStorageKey = taskId ? `task-${taskId}` : null

  const hasResult = useMemo(
    () => title.trim().length > 0 && prompt.trim().length > 0,
    [title, prompt]
  )
  const hasPrompt = useMemo(() => prompt.trim().length > 0, [prompt])

  useEffect(() => {
    if (!open || !conversationStorageKey) {
      setTitle('')
      setPrompt('')
      setModel('')
      setError('')
      return
    }
    const draft = getPromptDraft(conversationStorageKey)
    if (!draft) {
      setTitle('')
      setPrompt('')
      setModel('')
      return
    }
    setTitle(draft.title)
    setPrompt(draft.prompt)
    setModel(draft.model)
  }, [open, conversationStorageKey])

  useEffect(() => {
    if (!open) return

    let isCancelled = false
    const loadModels = async () => {
      setModelsLoading(true)
      try {
        const response = await modelApis.getUnifiedModels(undefined, false, 'all', undefined, 'llm')
        if (!isCancelled) {
          setModels(response.data ?? [])
        }
      } catch {
        if (!isCancelled) {
          setModels([])
        }
      } finally {
        if (!isCancelled) {
          setModelsLoading(false)
        }
      }
    }

    void loadModels()
    return () => {
      isCancelled = true
    }
  }, [open])

  const selectedModel = useMemo(() => {
    if (!model) return null
    return models.find(item => item.name === model) ?? null
  }, [model, models])

  const generate = async () => {
    if (!taskId) return
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    setIsLoading(true)
    setError('')
    setTitle('')
    setPrompt('')
    try {
      let livePrompt = ''
      const response = await taskApis.generatePromptDraftStream(
        taskId,
        {
          model: model || undefined,
          source: 'pet_panel',
        },
        {
          signal: controller.signal,
          onEvent: event => {
            if (event.type === 'prompt_delta' && event.delta) {
              livePrompt += event.delta
              setPrompt(livePrompt)
            }
            if (event.type === 'prompt_done' && event.prompt) {
              livePrompt = event.prompt
              setPrompt(event.prompt)
            }
            if (event.type === 'title_done' && event.title) {
              setTitle(event.title)
            }
          },
        }
      )

      setTitle(response.title)
      setPrompt(response.prompt)
      setModel(response.model)
      savePromptDraft(conversationStorageKey ?? taskId, {
        title: response.title,
        prompt: response.prompt,
        model: response.model,
        version: response.version,
        createdAt: response.created_at,
        sourceConversationId: String(taskId),
      })
    } catch (err) {
      if (controller.signal.aborted) {
        return
      }
      const message = err instanceof Error ? err.message : t('promptDraft.generateFailed')
      setError(message)
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
      setIsLoading(false)
    }
  }

  const closeAndReset = () => {
    abortControllerRef.current?.abort()
    setError('')
    onOpenChange(false)
  }

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
      abortControllerRef.current = null
    }
  }, [])

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          data-testid="prompt-draft-dialog"
          className="max-w-[720px] max-h-[80vh] overflow-hidden flex flex-col"
        >
          <DialogHeader>
            <DialogTitle>{t('promptDraft.dialogTitle')}</DialogTitle>
            <DialogDescription>{t('promptDraft.dialogDescription')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 flex-1 min-h-0 overflow-y-auto pr-1">
            <div className="space-y-2">
              <Label>{t('promptDraft.modelLabel')}</Label>
              <div data-testid="prompt-draft-model-selector">
                <SearchableSelect
                  value={selectedModel?.name || ''}
                  onValueChange={value => setModel(value)}
                  disabled={modelsLoading}
                  placeholder={t('promptDraft.modelPlaceholder')}
                  searchPlaceholder={t('promptDraft.modelSearch')}
                  emptyText={t('promptDraft.noModelFound')}
                  noMatchText={t('promptDraft.noModelFound')}
                  showChevron={true}
                  items={[
                    {
                      value: '',
                      label: t('promptDraft.useDefaultModel'),
                    },
                    ...models.map(item => ({
                      value: item.name,
                      label: item.displayName || item.name,
                      searchText: `${item.displayName || item.name} ${item.provider || ''}`,
                      content: (
                        <div className="flex flex-col">
                          <span>{item.displayName || item.name}</span>
                          {item.provider && (
                            <span className="text-xs text-muted-foreground">{item.provider}</span>
                          )}
                        </div>
                      ),
                    })),
                  ]}
                />
              </div>
            </div>

            {isLoading && (
              <div className="text-sm text-text-secondary">{t('promptDraft.loading')}</div>
            )}

            {!isLoading && error && (
              <div className="text-sm text-red-500" role="alert">
                {error}
              </div>
            )}

            {(hasPrompt || (!isLoading && hasResult)) && (
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-text-muted mb-1">{t('promptDraft.resultTitle')}</p>
                  <div className="text-sm font-medium text-text-primary break-all line-clamp-2">
                    {title || (isLoading ? '...' : '')}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-1">{t('promptDraft.resultPrompt')}</p>
                  <pre className="text-xs whitespace-pre-wrap bg-muted/40 border border-border rounded-md p-3 max-h-72 overflow-auto">
                    {prompt}
                  </pre>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            {taskId && hasResult ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => {
                    clearPromptDraft(conversationStorageKey ?? taskId)
                    setTitle('')
                    setPrompt('')
                  }}
                >
                  {t('promptDraft.clear')}
                </Button>
                <Button
                  data-testid="prompt-draft-regenerate-button"
                  variant="outline"
                  onClick={generate}
                  disabled={isLoading || !taskId}
                >
                  {t('promptDraft.regenerate')}
                </Button>
                <Button
                  data-testid="prompt-draft-fine-tune-button"
                  variant="outline"
                  onClick={() => setOpenFineTune(true)}
                  disabled={!hasResult}
                >
                  {t('promptDraft.fineTune')}
                </Button>
              </>
            ) : (
              <Button
                data-testid="prompt-draft-generate-button"
                variant="primary"
                onClick={generate}
                disabled={isLoading || !taskId}
              >
                {t('promptDraft.generate')}
              </Button>
            )}
            <Button variant="outline" onClick={closeAndReset}>
              {t('promptDraft.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PromptFineTuneDialog
        open={openFineTune}
        onOpenChange={setOpenFineTune}
        initialPrompt={prompt}
        modelName={model}
        onSave={updatedPrompt => {
          setPrompt(updatedPrompt)
          if (taskId && title.trim()) {
            savePromptDraft(conversationStorageKey ?? taskId, {
              title,
              prompt: updatedPrompt,
              model: model || 'default-model',
              version: 1,
              createdAt: new Date().toISOString(),
              sourceConversationId: String(taskId),
            })
          }
        }}
      />
    </>
  )
}
