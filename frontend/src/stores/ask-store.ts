import { create } from 'zustand'

import { api, ApiError } from '../api/client'
import type { AskEvent, AskSession, DeltaContextPacket } from '../api/types'

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function upsertPacket(packets: DeltaContextPacket[], nextPacket: DeltaContextPacket): DeltaContextPacket[] {
  const index = packets.findIndex((packet) => packet.packet_id === nextPacket.packet_id)
  if (index < 0) {
    return [...packets, nextPacket]
  }
  const next = [...packets]
  next[index] = { ...next[index], ...nextPacket }
  return next
}

type AskSidecarSnapshot = {
  projectId: string
  nodeId: string
  eventSeq: number
  packetList: DeltaContextPacket[]
}

function toAskSidecarSnapshot(session: AskSession): AskSidecarSnapshot {
  return {
    projectId: session.project_id,
    nodeId: session.node_id,
    eventSeq: session.event_seq,
    packetList: session.delta_context_packets,
  }
}

type AskStoreState = {
  sidecar: AskSidecarSnapshot | null
  isLoadingSidecar: boolean
  error: string | null
  loadSidecar: (projectId: string, nodeId: string) => Promise<void>
  resetSidecar: (projectId: string, nodeId: string) => Promise<void>
  approvePacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  rejectPacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  mergePacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  applyAskEvent: (event: AskEvent) => void
  clearSidecar: () => void
}

export const useAskStore = create<AskStoreState>((set) => ({
  sidecar: null,
  isLoadingSidecar: false,
  error: null,
  async loadSidecar(projectId: string, nodeId: string) {
    set({ isLoadingSidecar: true, error: null })
    try {
      const response = await api.getAskSidecar(projectId, nodeId)
      set({
        sidecar: toAskSidecarSnapshot(response.session),
        isLoadingSidecar: false,
        error: null,
      })
    } catch (error) {
      set({ error: toErrorMessage(error), isLoadingSidecar: false })
      throw error
    }
  },
  async resetSidecar(projectId: string, nodeId: string) {
    set({ error: null })
    try {
      const response = await api.resetAskSidecar(projectId, nodeId)
      set({
        sidecar: toAskSidecarSnapshot(response.session),
        error: null,
      })
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async approvePacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.approveAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        sidecar: state.sidecar
          ? {
              ...state.sidecar,
              packetList: upsertPacket(state.sidecar.packetList, response.packet),
            }
          : null,
        error: null,
      }))
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async rejectPacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.rejectAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        sidecar: state.sidecar
          ? {
              ...state.sidecar,
              packetList: upsertPacket(state.sidecar.packetList, response.packet),
            }
          : null,
        error: null,
      }))
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async mergePacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.mergeAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        sidecar: state.sidecar
          ? {
              ...state.sidecar,
              packetList: upsertPacket(state.sidecar.packetList, response.packet),
            }
          : null,
        error: null,
      }))
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  applyAskEvent(event) {
    set((state) => {
      const current = state.sidecar
      if (current && event.event_seq <= current.eventSeq) {
        return {}
      }

      if (!current) {
        if (event.type === 'ask_session_reset') {
          return { sidecar: toAskSidecarSnapshot(event.session) }
        }
        return {}
      }

      switch (event.type) {
        case 'ask_session_reset':
          return {
            sidecar: toAskSidecarSnapshot(event.session),
          }
        case 'ask_delta_context_suggested':
          return {
            sidecar: {
              ...current,
              eventSeq: event.event_seq,
              packetList: upsertPacket(current.packetList, event.packet),
            },
          }
        case 'ask_packet_status_changed':
          return {
            sidecar: {
              ...current,
              eventSeq: event.event_seq,
              packetList: upsertPacket(current.packetList, event.packet),
            },
          }
        default:
          return {}
      }
    })
  },
  clearSidecar() {
    set({
      sidecar: null,
      isLoadingSidecar: false,
      error: null,
    })
  },
}))
