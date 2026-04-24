import { useCallback, useEffect, useMemo, useState } from 'react'

import type { SessionThread } from '../contracts'
import { useThreadSessionStore } from '../store/threadSessionStore'
import type { ComposerModelOption } from './sessionRuntimeController'

type UseThreadModelSelectionOptions = {
  activeThreadId: string | null
  activeThread: SessionThread | null
}

function resolveSelectedModel(
  activeThreadId: string | null,
  activeThread: SessionThread | null,
  modelOptions: ComposerModelOption[],
  selectedModelByThread: Record<string, string>,
): string | null {
  if (!activeThreadId) {
    return null
  }

  const selectedFromState = selectedModelByThread[activeThreadId]
  if (typeof selectedFromState === 'string' && selectedFromState.trim().length > 0) {
    return selectedFromState
  }

  const threadModel = typeof activeThread?.model === 'string' ? activeThread.model.trim() : ''
  if (threadModel) {
    return threadModel
  }

  return modelOptions.find((option) => option.isDefault)?.value ?? modelOptions[0]?.value ?? null
}

export function useThreadModelSelection({
  activeThreadId,
  activeThread,
}: UseThreadModelSelectionOptions) {
  const [isModelLoading, setIsModelLoading] = useState(false)
  const [modelOptions, setModelOptions] = useState<ComposerModelOption[]>([])
  const [selectedModelByThread, setSelectedModelByThread] = useState<Record<string, string>>({})

  const selectedModel = useMemo(() => {
    return resolveSelectedModel(activeThreadId, activeThread, modelOptions, selectedModelByThread)
  }, [activeThread, activeThreadId, modelOptions, selectedModelByThread])

  useEffect(() => {
    if (!activeThreadId || !selectedModel) {
      return
    }

    setSelectedModelByThread((previous) => {
      if (previous[activeThreadId]) {
        return previous
      }
      return {
        ...previous,
        [activeThreadId]: selectedModel,
      }
    })
  }, [activeThreadId, selectedModel])

  const setModel = useCallback((model: string) => {
    const currentActiveThreadId = useThreadSessionStore.getState().activeThreadId
    if (!currentActiveThreadId) {
      return
    }

    setSelectedModelByThread((previous) => ({
      ...previous,
      [currentActiveThreadId]: model,
    }))
  }, [])

  return {
    isModelLoading,
    setIsModelLoading,
    modelOptions,
    setModelOptions,
    selectedModel,
    setModel,
  }
}
