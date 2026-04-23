import { create } from 'zustand'
import type { ConnectionState, SessionError } from '../contracts'

type ConnectionStoreState = {
  connection: ConnectionState
  reconnectAttempts: number
  setPhase: (phase: ConnectionState['phase']) => void
  setInitialized: (clientName: string | null, serverVersion: string | null) => void
  setError: (error: SessionError) => void
  markReconnectAttempt: () => void
  reset: () => void
}

const initialConnection: ConnectionState = {
  phase: 'disconnected',
  clientName: null,
  serverVersion: null,
  error: null,
}

export const useConnectionStore = create<ConnectionStoreState>((set) => ({
  connection: initialConnection,
  reconnectAttempts: 0,
  setPhase(phase) {
    set((state) => ({
      connection: {
        ...state.connection,
        phase,
        error: phase === 'error' ? state.connection.error ?? null : null,
      },
    }))
  },
  setInitialized(clientName, serverVersion) {
    set({
      connection: {
        phase: 'initialized',
        clientName,
        serverVersion,
        error: null,
      },
    })
  },
  setError(error) {
    set((state) => ({
      connection: {
        ...state.connection,
        phase: 'error',
        error,
      },
    }))
  },
  markReconnectAttempt() {
    set((state) => ({ reconnectAttempts: state.reconnectAttempts + 1 }))
  },
  reset() {
    set({ connection: initialConnection, reconnectAttempts: 0 })
  },
}))

