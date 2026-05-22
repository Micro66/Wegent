import { useMemo } from 'react'
import { ArrowLeft, Check } from 'lucide-react'
import type { UnifiedModel } from '@/types/api'

interface Props {
  onBack: () => void
  models: UnifiedModel[]
  selectedModel?: string
  onSelectModel: (model: UnifiedModel) => void
}

export function ModelPage({ onBack, models, selectedModel, onSelectModel }: Props) {
  const sortedModels = useMemo(() => {
    if (!selectedModel) return models

    const selectedIndex = models.findIndex(
      model => model.name === selectedModel || model.displayName === selectedModel,
    )
    if (selectedIndex <= 0) return models

    const selected = models[selectedIndex]
    return [
      selected,
      ...models.slice(0, selectedIndex),
      ...models.slice(selectedIndex + 1),
    ]
  }, [models, selectedModel])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      <div className="flex items-center gap-2 px-4 pt-3 pb-2">
        <button
          onClick={onBack}
          data-testid="model-back-button"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#f0f0f0]"
        >
          <ArrowLeft className="h-5 w-5 text-[#333]" />
        </button>
        <h1 className="text-[18px] font-bold text-black">选择模型</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-4">
        {sortedModels.length === 0 && (
          <div className="px-2 py-10 text-center text-[14px] text-[#999]">
            当前智能体没有可用模型
          </div>
        )}

        {sortedModels.map((model) => {
          const isSelected =
            model.name === selectedModel || model.displayName === selectedModel
          return (
            <button
              type="button"
              key={model.name}
              onClick={() => onSelectModel(model)}
              data-testid={`model-option-${model.name}`}
              className={`mb-1 flex min-h-[76px] w-full cursor-pointer items-center gap-3.5 rounded-2xl p-4 text-left ${
                isSelected ? 'bg-[#f5f5f5]' : ''
              }`}
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-black text-lg font-bold text-white">
                {model.name?.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[16px] font-semibold text-black">
                  {model.displayName ?? model.name}
                </div>
                <div className="mt-0.5 text-[13px] text-[#999]">
                  {model.provider}
                </div>
              </div>
              {isSelected && (
                <Check className="h-[18px] w-[18px] text-[#14B8A6]" />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
