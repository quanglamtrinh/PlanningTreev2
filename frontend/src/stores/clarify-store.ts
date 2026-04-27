import { create } from 'zustand'
import type { ClarifyQuestion, ClarifyState } from '../api/types'
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
  selectOption: (
    projectId: string,
    nodeId: string,
    fieldName: string,
    optionId: string | null,
  ) => void
  updateCustomAnswer: (
    projectId: string,
    nodeId: string,
    fieldName: string,
    text: string,
  ) => void
  flushAnswers: (projectId: string, nodeId: string) => Promise<void>
  confirmClarify: (projectId: string, nodeId: string) => Promise<void>
  invalidateEntry: (projectId: string, nodeId: string) => void
  reset: () => void
}

const EMPTY_ENTRY: ClarifyEntry = {
  clarify: {
    schema_version: 2,
    source_frame_revision: 0,
    confirmed_revision: 0,
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

function clarifyAnswerChanged(
  left: Pick<ClarifyQuestion, 'selected_option_id' | 'custom_answer'> | undefined,
  right: Pick<ClarifyQuestion, 'selected_option_id' | 'custom_answer'> | undefined,
): boolean {
  return (
    (left?.selected_option_id ?? null) !== (right?.selected_option_id ?? null) ||
    (left?.custom_answer ?? '') !== (right?.custom_answer ?? '')
  )
}

const pendingTimers = new Map<string, ReturnType<typeof globalThis.setTimeout>>()
const pendingSaves = new Map<string, Promise<void>>()
const loadRequestVersions = new Map<string, number>()

function clearPendingTimer(key: string) {
  const timer = pendingTimers.get(key)
  if (timer !== undefined) {
    globalThis.clearTimeout(timer)
    pendingTimers.delete(key)
  }
}

function nextLoadRequestVersion(key: string): number {
  const version = (loadRequestVersions.get(key) ?? 0) + 1
  loadRequestVersions.set(key, version)
  return version
}

function invalidateLoadRequests(key: string) {
  loadRequestVersions.set(key, (loadRequestVersions.get(key) ?? 0) + 1)
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

    // Compute dirty fields by comparing current questions to saved.
    // Keep a snapshot so we can preserve any newer edits made while save is in flight.
    const preSaveQuestions = entry.clarify.questions.map((q) => ({ ...q }))
    const preSaveByField = new Map(preSaveQuestions.map((q) => [q.field_name, q]))
    const savedByField = new Map(entry.savedQuestions.map((q) => [q.field_name, q]))
    const dirtyUpdates: { field_name: string; selected_option_id?: string | null; custom_answer?: string }[] = []
    for (const q of preSaveQuestions) {
      const saved = savedByField.get(q.field_name)
      if (
        !saved ||
        saved.selected_option_id !== q.selected_option_id ||
        saved.custom_answer !== q.custom_answer
      ) {
        dirtyUpdates.push({
          field_name: q.field_name,
          selected_option_id: q.selected_option_id,
          custom_answer: q.custom_answer,
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
          const currentEntry = s.entries[key]
          const latestByField = new Map(
            currentEntry.clarify.questions.map((q) => [q.field_name, q]),
          )
          const mergedQuestions = updated.questions.map((serverQuestion) => {
            const latestQuestion = latestByField.get(serverQuestion.field_name)
            const preSaveQuestion = preSaveByField.get(serverQuestion.field_name)
            if (!latestQuestion) {
              return serverQuestion
            }
            if (!clarifyAnswerChanged(latestQuestion, preSaveQuestion)) {
              return serverQuestion
            }
            return {
              ...serverQuestion,
              selected_option_id: latestQuestion.selected_option_id,
              custom_answer: latestQuestion.custom_answer,
            }
          })
          for (const latestQuestion of currentEntry.clarify.questions) {
            if (!updated.questions.some((q) => q.field_name === latestQuestion.field_name)) {
              mergedQuestions.push(latestQuestion)
            }
          }
          return {
            entries: {
              ...s.entries,
              [key]: {
                ...currentEntry,
                clarify: { ...updated, questions: mergedQuestions },
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
            return (
              !s ||
              s.selected_option_id !== q.selected_option_id ||
              s.custom_answer !== q.custom_answer
            )
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
            const preSave = preSaveByField.get(q.field_name)
            if (clarifyAnswerChanged(q, preSave)) {
              return q
            }
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
      const requestVersion = nextLoadRequestVersion(key)
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
        if (loadRequestVersions.get(key) !== requestVersion) {
          return
        }
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
        if (loadRequestVersions.get(key) !== requestVersion) {
          return
        }
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

    selectOption(
      projectId: string,
      nodeId: string,
      fieldName: string,
      optionId: string | null,
    ) {
      const key = stateKey(projectId, nodeId)
      set((s) => {
        const entry = s.entries[key] ?? EMPTY_ENTRY
        const updatedQuestions = entry.clarify.questions.map((q) =>
          q.field_name === fieldName
            ? { ...q, selected_option_id: optionId, custom_answer: '' }
            : q,
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

    updateCustomAnswer(
      projectId: string,
      nodeId: string,
      fieldName: string,
      text: string,
    ) {
      const key = stateKey(projectId, nodeId)
      set((s) => {
        const entry = s.entries[key] ?? EMPTY_ENTRY
        const updatedQuestions = entry.clarify.questions.map((q) =>
          q.field_name === fieldName
            ? { ...q, custom_answer: text, selected_option_id: null }
            : q,
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
      invalidateLoadRequests(key)
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
      loadRequestVersions.clear()
      set({ entries: {} })
    },
  }
})
