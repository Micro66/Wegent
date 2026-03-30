// SPDX-FileCopyrightText: 2026 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { modelApis, type UnifiedModel } from '@/apis/models'
import { taskApis } from '@/apis/tasks'
import {
  clearPromptDraft,
  appendPromptDraftVersion,
  getPromptDraftVersions,
  type PromptDraftLocal,
  type PromptDraftVersion,
  type PromptDraftVersionsState,
} from '@/features/prompt-draft/utils/promptDraftStorage'
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
import { PromptDraftComparisonPanel } from '@/features/prompt-draft/components/PromptDraftComparisonPanel'
import { PromptDraftVersionList } from '@/features/prompt-draft/components/PromptDraftVersionList'
import PromptFineTuneDialog from '@/features/prompt-tune/components/PromptFineTuneDialog'

interface PromptDraftDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number | null
}

type PromptDraftComparisonState =
  | {
      mode: 'candidate'
      previousVersion: PromptDraftVersion
      nextVersion: PromptDraftVersion
    }
  | {
      mode: 'history'
      previousVersion: PromptDraftVersion
      nextVersion: PromptDraftVersion
      selectedVersionId: string
    }

function buildPromptDraftVersionFromResponse(
  taskId: number,
  response: {
    title: string
    prompt: string
    model: string
    version: number
    created_at: string
  },
  source: PromptDraftVersion['source']
): PromptDraftVersion {
  return {
    id: `prompt-draft-${taskId}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    title: response.title,
    prompt: response.prompt,
    model: response.model,
    version: response.version,
    createdAt: response.created_at,
    sourceConversationId: String(taskId),
    source,
  }
}

function buildPromptDraftLocalFromVersion(version: PromptDraftVersion): PromptDraftLocal {
  return {
    title: version.title,
    prompt: version.prompt,
    model: version.model,
    version: version.version,
    createdAt: version.createdAt,
    sourceConversationId: version.sourceConversationId,
  }
}

function buildRollbackDraftFromVersion(version: PromptDraftVersion): PromptDraftLocal {
  return {
    ...buildPromptDraftLocalFromVersion(version),
    createdAt: new Date().toISOString(),
  }
}

export function PromptDraftDialog({ open, onOpenChange, taskId }: PromptDraftDialogProps) {
  const { t } = useTranslation('pet')
  const [models, setModels] = useState<UnifiedModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [model, setModel] = useState('')
  const [versionsState, setVersionsState] = useState<PromptDraftVersionsState | null>(null)
  const [comparisonState, setComparisonState] = useState<PromptDraftComparisonState | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [openFineTune, setOpenFineTune] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const requestVersionRef = useRef(0)
  const openRef = useRef(open)
  const conversationStorageKey = taskId ? `task-${taskId}` : null

  const currentVersion = useMemo(() => {
    if (!versionsState) return null
    return (
      versionsState.versions.find(version => version.id === versionsState.currentVersionId) ??
      versionsState.versions[0] ??
      null
    )
  }, [versionsState])

  const hasResult = useMemo(
    () =>
      Boolean(
        currentVersion &&
        currentVersion.title.trim().length > 0 &&
        currentVersion.prompt.trim().length > 0
      ),
    [currentVersion]
  )

  const isComparing = comparisonState !== null

  useEffect(() => {
    openRef.current = open
  }, [open])

  useEffect(() => {
    if (!open || !conversationStorageKey) {
      abortControllerRef.current?.abort()
      abortControllerRef.current = null
      requestVersionRef.current += 1
      setModel('')
      setError('')
      setIsLoading(false)
      setVersionsState(null)
      setComparisonState(null)
      setOpenFineTune(false)
      return
    }
    const versions = getPromptDraftVersions(conversationStorageKey)
    setVersionsState(versions)
    setComparisonState(null)
    setError('')
    if (!versions) {
      setModel('')
      return
    }
    const current = versions.versions.find(version => version.id === versions.currentVersionId)
    setModel(current?.model ?? '')
  }, [open, conversationStorageKey])

  useEffect(() => {
    if (isComparing || !currentVersion) return
    setModel(currentVersion.model)
  }, [currentVersion, isComparing])

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

  const resetPromptDraftState = () => {
    requestVersionRef.current += 1
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setVersionsState(null)
    setComparisonState(null)
    setIsLoading(false)
    setModel('')
    setError('')
    setOpenFineTune(false)
  }

  const persistVersion = (
    draft: PromptDraftLocal,
    source: 'initial' | 'regenerate' | 'rollback'
  ) => {
    if (!conversationStorageKey && !taskId) return null
    const nextState = appendPromptDraftVersion(conversationStorageKey ?? taskId, draft, source)
    setVersionsState(nextState)
    setComparisonState(null)
    return nextState
  }

  const acceptComparison = () => {
    if (!comparisonState) return

    if (comparisonState.mode === 'candidate') {
      const nextState = persistVersion(
        buildPromptDraftLocalFromVersion(comparisonState.nextVersion),
        'regenerate'
      )
      const nextCurrent = nextState?.versions[0] ?? comparisonState.nextVersion
      setModel(nextCurrent.model)
      return
    }

    const nextState = persistVersion(
      buildRollbackDraftFromVersion(comparisonState.nextVersion),
      'rollback'
    )
    const nextCurrent = nextState?.versions[0] ?? comparisonState.nextVersion
    setModel(nextCurrent.model)
  }

  const discardComparison = () => {
    setComparisonState(null)
  }

  const rollbackToVersion = (versionId: string) => {
    if (comparisonState) return
    if (!versionsState) return
    const targetVersion = versionsState.versions.find(version => version.id === versionId)
    if (!targetVersion) return

    const nextState = persistVersion(buildRollbackDraftFromVersion(targetVersion), 'rollback')
    const nextCurrent = nextState?.versions[0] ?? targetVersion
    setModel(nextCurrent.model)
  }

  const compareVersionToCurrent = (versionId: string) => {
    if (comparisonState) return
    if (!versionsState || !currentVersion) return
    const selectedVersion = versionsState.versions.find(version => version.id === versionId)
    if (!selectedVersion || selectedVersion.id === currentVersion.id) return

    setComparisonState({
      mode: 'history',
      previousVersion: currentVersion,
      nextVersion: selectedVersion,
      selectedVersionId: selectedVersion.id,
    })
  }

  const generate = async () => {
    if (!taskId) return
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    const requestVersion = requestVersionRef.current + 1
    requestVersionRef.current = requestVersion
    setIsLoading(true)
    setError('')

    const isRegenerating = Boolean(currentVersion && !comparisonState)
    if (!isRegenerating) {
      setComparisonState(null)
    }

    try {
      const response = await taskApis.generatePromptDraftStream(
        taskId,
        {
          model: model || undefined,
          source: 'pet_panel',
          current_prompt: isRegenerating && currentVersion ? currentVersion.prompt : undefined,
          regenerate: isRegenerating,
        },
        {
          signal: controller.signal,
          onEvent: event => {
            if (event.type === 'prompt_delta' && event.delta) return
            if (event.type === 'prompt_done' && event.prompt) return
            if (event.type === 'title_done' && event.title) return
          },
        }
      )

      if (
        controller.signal.aborted ||
        requestVersionRef.current !== requestVersion ||
        !openRef.current
      ) {
        return
      }

      if (isRegenerating && currentVersion) {
        setComparisonState({
          mode: 'candidate',
          previousVersion: currentVersion,
          nextVersion: buildPromptDraftVersionFromResponse(taskId, response, 'regenerate'),
        })
        return
      }

      const nextState = persistVersion(
        {
          title: response.title,
          prompt: response.prompt,
          model: response.model,
          version: response.version,
          createdAt: response.created_at,
          sourceConversationId: String(taskId),
        },
        'initial'
      )
      const nextCurrent = nextState?.versions[0]
      setModel(nextCurrent?.model ?? response.model)
    } catch (err) {
      if (
        controller.signal.aborted ||
        requestVersionRef.current !== requestVersion ||
        !openRef.current
      ) {
        return
      }
      const message = err instanceof Error ? err.message : t('promptDraft.generateFailed')
      setError(message)
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null
      }
      if (requestVersionRef.current === requestVersion && openRef.current) {
        setIsLoading(false)
      }
    }
  }

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetPromptDraftState()
    }
    onOpenChange(nextOpen)
  }

  const closeAndReset = () => {
    resetPromptDraftState()
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
      <Dialog open={open} onOpenChange={handleOpenChange}>
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

            {comparisonState ? (
              <PromptDraftComparisonPanel
                previousVersion={comparisonState.previousVersion}
                nextVersion={comparisonState.nextVersion}
                onKeepOld={discardComparison}
                onUseNew={acceptComparison}
                isDecisionPending={false}
                title={
                  comparisonState.mode === 'history'
                    ? t('promptDraft.compare.historyTitle')
                    : t('promptDraft.compare.title')
                }
                previousLabel={
                  comparisonState.mode === 'history'
                    ? t('promptDraft.compare.current')
                    : t('promptDraft.compare.previous')
                }
                nextLabel={
                  comparisonState.mode === 'history'
                    ? t('promptDraft.compare.selected')
                    : t('promptDraft.compare.next')
                }
                keepActionLabel={
                  comparisonState.mode === 'history'
                    ? t('promptDraft.compare.cancel')
                    : t('promptDraft.keepOld')
                }
                useActionLabel={
                  comparisonState.mode === 'history'
                    ? t('promptDraft.compare.rollbackToSelected')
                    : t('promptDraft.useNew')
                }
                className="min-h-0 flex-1"
              />
            ) : (
              hasResult && (
                <div className="space-y-3">
                  <div>
                    <p className="text-xs text-text-muted mb-1">{t('promptDraft.resultTitle')}</p>
                    <div className="text-sm font-medium text-text-primary break-all line-clamp-2">
                      {currentVersion?.title}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-text-muted mb-1">{t('promptDraft.resultPrompt')}</p>
                    <pre className="text-xs whitespace-pre-wrap bg-muted/40 border border-border rounded-md p-3 max-h-72 overflow-auto">
                      {currentVersion?.prompt}
                    </pre>
                  </div>
                </div>
              )
            )}

            {versionsState?.versions.length ? (
              <PromptDraftVersionList
                versions={versionsState.versions}
                currentVersionId={versionsState.currentVersionId}
                onRollback={rollbackToVersion}
                onCompareToCurrent={compareVersionToCurrent}
                isDecisionPending={Boolean(comparisonState)}
                className="pt-1"
              />
            ) : null}

            {hasResult && !comparisonState && (
              <div className="text-xs text-text-muted">
                {t('promptDraft.currentVersionLabel') || 'promptDraft.currentVersionLabel'}
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
                    resetPromptDraftState()
                  }}
                >
                  {t('promptDraft.clear')}
                </Button>
                <Button
                  data-testid="prompt-draft-regenerate-button"
                  variant="outline"
                  onClick={generate}
                  disabled={isLoading || !taskId || isComparing}
                >
                  {t('promptDraft.regenerate')}
                </Button>
                <Button
                  data-testid="prompt-draft-fine-tune-button"
                  variant="outline"
                  onClick={() => setOpenFineTune(true)}
                  disabled={!hasResult || isComparing}
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
        initialPrompt={currentVersion?.prompt ?? ''}
        modelName={model}
        onSave={updatedPrompt => {
          if (!taskId || !currentVersion) return
          const nextState = persistVersion(
            {
              title: currentVersion.title,
              prompt: updatedPrompt,
              model: model || currentVersion.model || 'default-model',
              version: currentVersion.version,
              createdAt: new Date().toISOString(),
              sourceConversationId: String(taskId),
            },
            'regenerate'
          )
          const nextCurrent = nextState?.versions[0]
          setModel(nextCurrent?.model ?? (model || currentVersion.model))
        }}
      />
    </>
  )
}
