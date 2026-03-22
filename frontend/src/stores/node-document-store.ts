import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type { NodeDocument, NodeDocumentKind } from '../api/types'

const AUTOSAVE_DELAY_MS = 800

type NodeDocumentEntry = {
  content: string
  savedContent: string
  updatedAt: string | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  hasLoaded: boolean
}

type NodeDocumentStoreState = {
  entries: Record<string, NodeDocumentEntry>
  loadDocument: (projectId: string, nodeId: string, kind: NodeDocumentKind) => Promise<void>
  updateDraft: (projectId: string, nodeId: string, kind: NodeDocumentKind, content: string) => void
  flushDocument: (projectId: string, nodeId: string, kind: NodeDocumentKind) => Promise<void>
  invalidateEntry: (projectId: string, nodeId: string, kind: NodeDocumentKind) => void
  reset: () => void
}

const EMPTY_ENTRY: NodeDocumentEntry = {
  content: '',
  savedContent: '',
  updatedAt: null,
  isLoading: false,
  isSaving: false,
  error: null,
  hasLoaded: false,
}

const pendingTimers = new Map<string, ReturnType<typeof globalThis.setTimeout>>()
const pendingSaves = new Map<string, Promise<void>>()

function documentKey(projectId: string, nodeId: string, kind: NodeDocumentKind) {
  return `${projectId}::${nodeId}::${kind}`
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function clearPendingTimer(key: string) {
  const timer = pendingTimers.get(key)
  if (timer !== undefined) {
    globalThis.clearTimeout(timer)
    pendingTimers.delete(key)
  }
}

function normalizeDocument(document: NodeDocument): Pick<NodeDocumentEntry, 'content' | 'savedContent' | 'updatedAt'> {
  return {
    content: document.content,
    savedContent: document.content,
    updatedAt: document.updated_at,
  }
}

export const useNodeDocumentStore = create<NodeDocumentStoreState>((set, get) => {
  async function flushDocument(projectId: string, nodeId: string, kind: NodeDocumentKind): Promise<void> {
    const key = documentKey(projectId, nodeId, kind)
    clearPendingTimer(key)

    const inFlight = pendingSaves.get(key)
    if (inFlight) {
      await inFlight
      return
    }

    const entry = get().entries[key]
    if (!entry || !entry.hasLoaded || entry.isLoading || entry.content === entry.savedContent) {
      return
    }

    const contentToSave = entry.content
    set((state) => ({
      entries: {
        ...state.entries,
        [key]: {
          ...state.entries[key],
          isSaving: true,
          error: null,
        },
      },
    }))

    const savePromise = api
      .putNodeDocument(projectId, nodeId, kind, contentToSave)
      .then((document) => {
        set((state) => {
          const current = state.entries[key] ?? EMPTY_ENTRY
          return {
            entries: {
              ...state.entries,
              [key]: {
                ...current,
                savedContent: contentToSave,
                updatedAt: document.updated_at,
                isSaving: false,
                error: null,
                hasLoaded: true,
              },
            },
          }
        })

        const current = get().entries[key]
        if (current && current.content !== current.savedContent) {
          scheduleAutosave(projectId, nodeId, kind)
        }
      })
      .catch((error) => {
        set((state) => {
          const current = state.entries[key] ?? EMPTY_ENTRY
          return {
            entries: {
              ...state.entries,
              [key]: {
                ...current,
                isSaving: false,
                error: toErrorMessage(error),
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

  function scheduleAutosave(projectId: string, nodeId: string, kind: NodeDocumentKind) {
    const key = documentKey(projectId, nodeId, kind)
    clearPendingTimer(key)
    pendingTimers.set(
      key,
      globalThis.setTimeout(() => {
        pendingTimers.delete(key)
        void get().flushDocument(projectId, nodeId, kind).catch(() => undefined)
      }, AUTOSAVE_DELAY_MS),
    )
  }

  return {
    entries: {},
    async loadDocument(projectId: string, nodeId: string, kind: NodeDocumentKind) {
      const key = documentKey(projectId, nodeId, kind)
      const existing = get().entries[key]
      if (existing?.hasLoaded || existing?.isLoading) {
        return
      }
      set((state) => ({
        entries: {
          ...state.entries,
          [key]: {
            ...(state.entries[key] ?? EMPTY_ENTRY),
            isLoading: true,
            error: null,
          },
        },
      }))

      try {
        const document = await api.getNodeDocument(projectId, nodeId, kind)
        set((state) => ({
          entries: {
            ...state.entries,
            [key]: {
              ...(state.entries[key] ?? EMPTY_ENTRY),
              ...normalizeDocument(document),
              isLoading: false,
              isSaving: false,
              error: null,
              hasLoaded: true,
            },
          },
        }))
      } catch (error) {
        set((state) => ({
          entries: {
            ...state.entries,
            [key]: {
              ...(state.entries[key] ?? EMPTY_ENTRY),
              isLoading: false,
              error: toErrorMessage(error),
            },
          },
        }))
        throw error
      }
    },
    updateDraft(projectId: string, nodeId: string, kind: NodeDocumentKind, content: string) {
      const key = documentKey(projectId, nodeId, kind)
      set((state) => ({
        entries: {
          ...state.entries,
          [key]: {
            ...(state.entries[key] ?? EMPTY_ENTRY),
            content,
            error: null,
            hasLoaded: true,
          },
        },
      }))
      scheduleAutosave(projectId, nodeId, kind)
    },
    flushDocument,
    invalidateEntry(projectId: string, nodeId: string, kind: NodeDocumentKind) {
      const key = documentKey(projectId, nodeId, kind)
      clearPendingTimer(key)
      pendingSaves.delete(key)
      set((state) => {
        const { [key]: _, ...rest } = state.entries
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

export function getNodeDocumentEntry(
  projectId: string,
  nodeId: string,
  kind: NodeDocumentKind,
): NodeDocumentEntry {
  return useNodeDocumentStore.getState().entries[documentKey(projectId, nodeId, kind)] ?? EMPTY_ENTRY
}
