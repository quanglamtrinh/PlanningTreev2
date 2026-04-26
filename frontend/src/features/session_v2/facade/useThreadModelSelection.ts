import { useCallback, useEffect, useMemo, useState } from 'react'

import type { SessionThread } from '../contracts'
import { useThreadSessionStore } from '../store/threadSessionStore'
import {
  CODEX_MODEL_FALLBACK_OPTIONS,
  DEFAULT_CODEX_MODEL_OPTION,
  type ComposerModelOption,
} from './sessionRuntimeController'

const COMPOSER_FALLBACK_MODEL_KEY = '__composer__'

type UseThreadModelSelectionOptions = {
  activeThreadId: string | null
  activeThread: SessionThread | null
}

function resolveSelectedModel(
  activeThreadId: string | null,
  activeThread: SessionThread | null,
  selectedModelByThread: Record<string, string>,
): string | null {
  if (!activeThreadId) {
    return selectedModelByThread[COMPOSER_FALLBACK_MODEL_KEY] ??
      DEFAULT_CODEX_MODEL_OPTION.value
  }

  const selectedFromState = selectedModelByThread[activeThreadId]
  if (typeof selectedFromState === 'string' && selectedFromState.trim().length > 0) {
    return selectedFromState
  }

  const threadModel = typeof activeThread?.model === 'string' ? activeThread.model.trim() : ''
  if (threadModel) {
    return threadModel
  }

  return DEFAULT_CODEX_MODEL_OPTION.value
}

function ensureFallbackModelOptions(options: ComposerModelOption[]): ComposerModelOption[] {
  const rows = [...CODEX_MODEL_FALLBACK_OPTIONS]
  const seen = new Set(rows.map((option) => option.value))
  for (const option of options) {
    if (seen.has(option.value)) {
      continue
    }
    seen.add(option.value)
    rows.push(option)
  }
  return rows
}

export function useThreadModelSelection({
  activeThreadId,
  activeThread,
}: UseThreadModelSelectionOptions) {
  const [isModelLoading, setIsModelLoading] = useState(false)
  const [modelOptions, setModelOptions] = useState<ComposerModelOption[]>([])
  const [selectedModelByThread, setSelectedModelByThread] = useState<Record<string, string>>({})

  const selectedModel = useMemo(() => {
    return resolveSelectedModel(activeThreadId, activeThread, selectedModelByThread)
  }, [activeThread, activeThreadId, selectedModelByThread])
  const composerModelOptions = useMemo(() => ensureFallbackModelOptions(modelOptions), [modelOptions])

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
    const selectionKey = currentActiveThreadId ?? COMPOSER_FALLBACK_MODEL_KEY

    setSelectedModelByThread((previous) => ({
      ...previous,
      [selectionKey]: model,
    }))
  }, [])

  return {
    isModelLoading,
    setIsModelLoading,
    modelOptions: composerModelOptions,
    setModelOptions,
    selectedModel,
    setModel,
  }
}
