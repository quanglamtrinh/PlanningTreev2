import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  getAskSidecar: vi.fn(),
  resetAskSidecar: vi.fn(),
  approveAskPacket: vi.fn(),
  rejectAskPacket: vi.fn(),
  mergeAskPacket: vi.fn(),
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {
    status: number
    code: string | null

    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  },
}))

import { useAskStore } from '../../src/stores/ask-store'

function makeSession(overrides: Record<string, unknown> = {}) {
  return {
    project_id: 'project-1',
    node_id: 'node-1',
    active_turn_id: null,
    event_seq: 1,
    status: 'idle',
    messages: [],
    delta_context_packets: [],
    ...overrides,
  }
}

function makePacket(overrides: Record<string, unknown> = {}) {
  return {
    packet_id: 'packet-1',
    node_id: 'node-1',
    created_at: '2026-03-16T00:00:00Z',
    source_message_ids: [],
    summary: 'Risk',
    context_text: 'Key risk',
    status: 'pending',
    status_reason: null,
    merged_at: null,
    merged_planning_turn_id: null,
    suggested_by: 'agent',
    ...overrides,
  }
}

describe('ask-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAskStore.setState(useAskStore.getInitialState())
  })

  it('loads sidecar state without owning transcript rendering state', async () => {
    apiMock.getAskSidecar.mockResolvedValue({
      session: makeSession({
        event_seq: 4,
        messages: [{ message_id: 'legacy_msg', content: 'legacy' }],
        delta_context_packets: [makePacket()],
      }),
    })

    await useAskStore.getState().loadSidecar('project-1', 'node-1')

    expect(apiMock.getAskSidecar).toHaveBeenCalledWith('project-1', 'node-1')
    expect(useAskStore.getState().sidecar).toEqual({
      projectId: 'project-1',
      nodeId: 'node-1',
      eventSeq: 4,
      packetList: [makePacket()],
    })
  })

  it('applies only packet/reset ask events and ignores transcript-only events', () => {
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'node-1',
        eventSeq: 1,
        packetList: [],
      },
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_message_created',
      event_seq: 2,
      active_turn_id: 'turn_1',
      user_message: {
        message_id: 'msg_user',
        role: 'user',
        content: 'hello',
        status: 'completed',
        created_at: '2026-03-16T00:00:00Z',
        updated_at: '2026-03-16T00:00:00Z',
        error: null,
      },
      assistant_message: {
        message_id: 'msg_assistant',
        role: 'assistant',
        content: '',
        status: 'pending',
        created_at: '2026-03-16T00:00:00Z',
        updated_at: '2026-03-16T00:00:00Z',
        error: null,
      },
    })

    expect(useAskStore.getState().sidecar?.eventSeq).toBe(1)

    useAskStore.getState().applyAskEvent({
      type: 'ask_delta_context_suggested',
      event_seq: 3,
      packet: makePacket(),
    })

    expect(useAskStore.getState().sidecar?.eventSeq).toBe(3)
    expect(useAskStore.getState().sidecar?.packetList).toHaveLength(1)
  })

  it('upserts packet status changes and resets from the preserved sidecar stream', () => {
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'node-1',
        eventSeq: 2,
        packetList: [makePacket()],
      },
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_packet_status_changed',
      event_seq: 4,
      packet: makePacket({ status: 'approved' }),
    })

    expect(useAskStore.getState().sidecar?.packetList[0]?.status).toBe('approved')

    useAskStore.getState().applyAskEvent({
      type: 'ask_session_reset',
      event_seq: 5,
      session: makeSession({ event_seq: 5, delta_context_packets: [] }),
    })

    expect(useAskStore.getState().sidecar?.packetList).toEqual([])
    expect(useAskStore.getState().sidecar?.eventSeq).toBe(5)
  })

  it('local packet actions upsert returned packets without widening ownership again', async () => {
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'node-1',
        eventSeq: 7,
        packetList: [makePacket()],
      },
    })
    apiMock.approveAskPacket.mockResolvedValue({ packet: makePacket({ status: 'approved' }) })
    apiMock.mergeAskPacket.mockResolvedValue({
      packet: makePacket({ status: 'merged', merged_at: '2026-03-16T00:05:00Z' }),
    })

    await useAskStore.getState().approvePacket('project-1', 'node-1', 'packet-1')
    expect(useAskStore.getState().sidecar?.packetList[0]?.status).toBe('approved')
    expect(useAskStore.getState().sidecar?.eventSeq).toBe(7)

    await useAskStore.getState().mergePacket('project-1', 'node-1', 'packet-1')
    expect(useAskStore.getState().sidecar?.packetList[0]?.status).toBe('merged')
  })
})
