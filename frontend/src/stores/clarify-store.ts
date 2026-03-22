import { create } from 'zustand'
import type { ClarifyQuestion, ClarifyResolutionStatus, ClarifyState } from '../api/types'
import { api } from '../api/client'
import { useDetailStateStore } from './detail-state-store'

const AUTOSAVE_DELAY_MS = 800

type ClarifyEntry = {
  clarify: ClarifyState
  savedQuestions: ClarifyQuestion[]
  isLoading: boolean
  isSaving: boolean
  loadError: string
  saveError: string
  hasLoaded: boolean
}

type ClarifyStoreState = {
  entries: Record<string, ClarifyEntry>

  loadClarify: (projectId: string, nodeId: string) => Promise<void>
  updateDraft: (
    projectId: string,
    nodeId: string,
    fieldName: string,
    answer: string,
    status: ClarifyResolutionStatus,
  ) => void
  flushAnswers: (projectId: string, nodeId: string) => Promise<void>
  confirmClarify: (projectId: string, nodeId: string) => Promise<void>
  invalidateEntry: (projectId: string, nodeId: string) => void
  reset: () => void
}

const EMPTY_ENTRY: ClarifyEntry = {
  clarify: {
    schema_version: 1,
    source_frame_revision: 0,
    confirmed_at: null,
    questions: [],
    updated_at: null,
  },
  savedQuestions: [],
  isLoading: false,
  isSaving: false,
  loadError: '',
  saveError: '',
  hasLoaded: false,
}

function stateKey(projectId: string, nodeId: string): string {
  return `${projectId}::${nodeId}`
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

const pendingTimers = new Map<string, ReturnType<typeof globalThis.setTimeout>>()
const pendingSaves = new Map<string, Promise<void>>()

function clearPendingTimer(key: string) {
  const timer = pendingTimers.get(key)
  if (timer !== undefined) {
    globalThis.clearTimeout(timer)
    pendingTimers.delete(key)
  }
}

export const useClarifyStore = create<ClarifyStoreState>((set, get) => {
  function scheduleAutosave(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    clearPendingTimer(key)
    pendingTimers.set(
      key,
      globalThis.setTimeout(() => {
        pendingTimers.delete(key)
        void get().flushAnswers(projectId, nodeId).catch(() => undefined)
      }, AUTOSAVE_DELAY_MS),
    )
  }

  async function flushAnswers(projectId: string, nodeId: string): Promise<void> {
    const key = stateKey(projectId, nodeId)
    clearPendingTimer(key)

    const inFlight = pendingSaves.get(key)
    if (inFlight) {
      await inFlight
      return
    }

    const entry = get().entries[key]
    if (!entry || !entry.hasLoaded || entry.isLoading) return

    // Compute dirty fields by comparing current questions to saved
    const savedByField = new Map(entry.savedQuestions.map((q) => [q.field_name, q]))
    const dirtyUpdates: Pick<ClarifyQuestion, 'field_name' | 'answer' | 'resolution_status'>[] = []
    for (const q of entry.clarify.questions) {
      const saved = savedByField.get(q.field_name)
      if (!saved || saved.answer !== q.answer || saved.resolution_status !== q.resolution_status) {
        dirtyUpdates.push({
          field_name: q.field_name,
          answer: q.answer,
          resolution_status: q.resolution_status,
        })
      }
    }

    if (dirtyUpdates.length === 0) return

    set((s) => ({
      entries: {
        ...s.entries,
        [key]: { ...(s.entries[key] ?? EMPTY_ENTRY), isSaving: true, saveError: '' },
      },
    }))

    const savePromise = api
      .updateClarify(projectId, nodeId, dirtyUpdates)
      .then((updated) => {
        set((s) => {
          if (!s.entries[key]) return s // entry was invalidated
          return {
            entries: {
              ...s.entries,
              [key]: {
                ...s.entries[key],
                clarify: updated,
                savedQuestions: updated.questions,
                isSaving: false,
                saveError: '',
              },
            },
          }
        })

        // If more changes happened while saving, schedule another save
        const current = get().entries[key]
        if (current) {
          const newSaved = new Map(current.savedQuestions.map((q) => [q.field_name, q]))
          const stillDirty = current.clarify.questions.some((q) => {
            const s = newSaved.get(q.field_name)
            return !s || s.answer !== q.answer || s.resolution_status !== q.resolution_status
          })
          if (stillDirty) {
            scheduleAutosave(projectId, nodeId)
          }
        }
      })
      .catch((error) => {
        set((s) => {
          if (!s.entries[key]) return s // entry was invalidated
          const current = s.entries[key]
          const rolledBackQuestions = current.clarify.questions.map((q) => {
            const saved = savedByField.get(q.field_name)
            return saved ? { ...saved } : q
          })
          return {
            entries: {
              ...s.entries,
              [key]: {
                ...current,
                clarify: { ...current.clarify, questions: rolledBackQuestions },
                isSaving: false,
                saveError: toErrorMessage(error),
              },
            },
          }
        })
        throw error
      })
      .finally(() => {
        pendingSaves.delete(key)
      })

    pendingSaves.set(key, savePromise)
    await savePromise
  }

  return {
    entries: {},

    async loadClarify(projectId: string, nodeId: string) {
      const key = stateKey(projectId, nodeId)
      const existing = get().entries[key]
      if (existing?.hasLoaded || existing?.isLoading) return
      set((s) => ({
        entries: {
          ...s.entries,
          [key]: {
            ...(s.entries[key] ?? EMPTY_ENTRY),
            isLoading: true,
            loadError: '',
          },
        },
      }))
      try {
        const state = await api.getClarify(projectId, nodeId)
        set((s) => ({
          entries: {
            ...s.entries,
            [key]: {
              ...(s.entries[key] ?? EMPTY_ENTRY),
              clarify: state,
              savedQuestions: state.questions,
              isLoading: false,
              loadError: '',
              hasLoaded: true,
            },
          },
        }))
      } catch (error) {
        set((s) => ({
          entries: {
            ...s.entries,
            [key]: {
              ...(s.entries[key] ?? EMPTY_ENTRY),
              isLoading: false,
              loadError: toErrorMessage(error),
            },
          },
        }))
      }
    },

    updateDraft(
      projectId: string,
      nodeId: string,
      fieldName: string,
      answer: string,
      status: ClarifyResolutionStatus,
    ) {
      const key = stateKey(projectId, nodeId)
      set((s) => {
        const entry = s.entries[key] ?? EMPTY_ENTRY
        const updatedQuestions = entry.clarify.questions.map((q) =>
          q.field_name === fieldName ? { ...q, answer, resolution_status: status } : q,
        )
        return {
          entries: {
            ...s.entries,
            [key]: {
              ...entry,
              clarify: { ...entry.clarify, questions: updatedQuestions },
              saveError: '',
            },
          },
        }
      })
      scheduleAutosave(projectId, nodeId)
    },

    flushAnswers,

    async confirmClarify(projectId: string, nodeId: string) {
      const key = stateKey(projectId, nodeId)

      // Flush any pending saves first
      await flushAnswers(projectId, nodeId)

      set((s) => ({
        entries: {
          ...s.entries,
          [key]: { ...(s.entries[key] ?? EMPTY_ENTRY), isSaving: true, saveError: '' },
        },
      }))
      try {
        const detailState = await api.confirmClarify(projectId, nodeId)
        useDetailStateStore.setState((s) => ({
          entries: { ...s.entries, [key]: detailState },
        }))
        set((s) => ({
          entries: {
            ...s.entries,
            [key]: { ...(s.entries[key] ?? EMPTY_ENTRY), isSaving: false },
          },
        }))
      } catch (error) {
        set((s) => ({
          entries: {
            ...s.entries,
            [key]: {
              ...(s.entries[key] ?? EMPTY_ENTRY),
              isSaving: false,
              saveError: toErrorMessage(error),
            },
          },
        }))
        throw error
      }
    },

    invalidateEntry(projectId: string, nodeId: string) {
      const key = stateKey(projectId, nodeId)
      clearPendingTimer(key)
      pendingSaves.delete(key)
      set((s) => {
        const { [key]: _, ...rest } = s.entries
        return { entries: rest }
      })
    },

    reset() {
      for (const key of pendingTimers.keys()) {
        clearPendingTimer(key)
      }
      pendingSaves.clear()
      set({ entries: {} })
    },
  }
})
