import { create } from 'zustand'

export type ShapingArtifact = 'frame' | 'clarify' | 'spec'
export type ShapingActionKind = 'generate' | 'confirm'
export type ShapingActionStatus = 'idle' | 'running' | 'succeeded' | 'failed'

export type ShapingActionState = {
  status: ShapingActionStatus
  updatedAt: string | null
  message: string | null
}

type ArtifactActionState = {
  generate: ShapingActionState
  confirm: ShapingActionState
}

export type AskShellNodeActionState = {
  frame: ArtifactActionState
  clarify: ArtifactActionState
  spec: ArtifactActionState
}

type AskShellActionStoreState = {
  entries: Record<string, AskShellNodeActionState>
  markRunning: (
    projectId: string,
    nodeId: string,
    artifact: ShapingArtifact,
    action: ShapingActionKind,
    message?: string | null,
  ) => void
  markSucceeded: (
    projectId: string,
    nodeId: string,
    artifact: ShapingArtifact,
    action: ShapingActionKind,
    message?: string | null,
  ) => void
  markFailed: (
    projectId: string,
    nodeId: string,
    artifact: ShapingArtifact,
    action: ShapingActionKind,
    message?: string | null,
  ) => void
  clearNode: (projectId: string, nodeId: string) => void
  reset: () => void
}

const DEFAULT_ACTION_STATE: ShapingActionState = {
  status: 'idle',
  updatedAt: null,
  message: null,
}

function cloneDefaultArtifactState(): ArtifactActionState {
  return {
    generate: { ...DEFAULT_ACTION_STATE },
    confirm: { ...DEFAULT_ACTION_STATE },
  }
}

function cloneDefaultNodeState(): AskShellNodeActionState {
  return {
    frame: cloneDefaultArtifactState(),
    clarify: cloneDefaultArtifactState(),
    spec: cloneDefaultArtifactState(),
  }
}

export function askShellNodeActionStateKey(projectId: string, nodeId: string): string {
  return `${projectId}::${nodeId}`
}

function withNodeState(
  current: AskShellNodeActionState | undefined,
  artifact: ShapingArtifact,
  action: ShapingActionKind,
  next: ShapingActionState,
): AskShellNodeActionState {
  const base = current ?? cloneDefaultNodeState()
  return {
    ...base,
    [artifact]: {
      ...base[artifact],
      [action]: next,
    },
  }
}

export const useAskShellActionStore = create<AskShellActionStoreState>((set) => ({
  entries: {},

  markRunning(projectId, nodeId, artifact, action, message = null) {
    const key = askShellNodeActionStateKey(projectId, nodeId)
    const next: ShapingActionState = {
      status: 'running',
      updatedAt: new Date().toISOString(),
      message,
    }
    set((state) => ({
      entries: {
        ...state.entries,
        [key]: withNodeState(state.entries[key], artifact, action, next),
      },
    }))
  },

  markSucceeded(projectId, nodeId, artifact, action, message = null) {
    const key = askShellNodeActionStateKey(projectId, nodeId)
    const next: ShapingActionState = {
      status: 'succeeded',
      updatedAt: new Date().toISOString(),
      message,
    }
    set((state) => ({
      entries: {
        ...state.entries,
        [key]: withNodeState(state.entries[key], artifact, action, next),
      },
    }))
  },

  markFailed(projectId, nodeId, artifact, action, message = null) {
    const key = askShellNodeActionStateKey(projectId, nodeId)
    const next: ShapingActionState = {
      status: 'failed',
      updatedAt: new Date().toISOString(),
      message,
    }
    set((state) => ({
      entries: {
        ...state.entries,
        [key]: withNodeState(state.entries[key], artifact, action, next),
      },
    }))
  },

  clearNode(projectId, nodeId) {
    const key = askShellNodeActionStateKey(projectId, nodeId)
    set((state) => {
      const { [key]: _discard, ...rest } = state.entries
      return { entries: rest }
    })
  },

  reset() {
    set({ entries: {} })
  },
}))
