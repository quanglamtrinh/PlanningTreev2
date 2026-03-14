import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getAskSession: vi.fn(),
    sendAskMessage: vi.fn(),
    resetAskSession: vi.fn(),
    approveAskPacket: vi.fn(),
    rejectAskPacket: vi.fn(),
    mergeAskPacket: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => {
  class ApiError extends Error {
    status: number
    code: string | null

    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  }

  return {
    api: apiMock,
    ApiError,
  }
})

import type { AskSession, DeltaContextPacket } from '../../src/api/types'
import { useAskStore } from '../../src/stores/ask-store'

function makePacket(overrides: Partial<DeltaContextPacket> = {}): DeltaContextPacket {
  return {
    packet_id: 'packet-1',
    node_id: 'node-1',
    created_at: '2026-03-10T00:00:00Z',
    source_message_ids: ['msg-user', 'msg-assistant'],
    summary: 'Watch scope',
    context_text: 'The scope is narrower than expected.',
    status: 'pending',
    status_reason: null,
    merged_at: null,
    merged_planning_turn_id: null,
    suggested_by: 'agent',
    ...overrides,
  }
}

function makeSession(overrides: Partial<AskSession> = {}): AskSession {
  return {
    project_id: 'project-1',
    node_id: 'node-1',
    active_turn_id: null,
    event_seq: 0,
    status: null,
    messages: [],
    delta_context_packets: [],
    ...overrides,
  }
}

describe('ask-store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAskStore.setState(useAskStore.getInitialState())
  })

  it('applies ask_message_created, ask_assistant_delta, and ask_assistant_completed', () => {
    useAskStore.setState({ session: makeSession() })

    useAskStore.getState().applyAskEvent({
      type: 'ask_message_created',
      event_seq: 1,
      active_turn_id: 'turn_1',
      user_message: {
        message_id: 'msg_user',
        role: 'user',
        content: 'What is the main risk?',
        status: 'completed',
        created_at: '2026-03-10T00:00:00Z',
        updated_at: '2026-03-10T00:00:00Z',
        error: null,
      },
      assistant_message: {
        message_id: 'msg_assistant',
        role: 'assistant',
        content: '',
        status: 'pending',
        created_at: '2026-03-10T00:00:00Z',
        updated_at: '2026-03-10T00:00:00Z',
        error: null,
      },
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_assistant_delta',
      event_seq: 2,
      message_id: 'msg_assistant',
      delta: 'The ',
      content: 'The ',
      updated_at: '2026-03-10T00:00:01Z',
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_assistant_completed',
      event_seq: 3,
      message_id: 'msg_assistant',
      content: 'The main risk is hidden dependency churn.',
      updated_at: '2026-03-10T00:00:02Z',
    })

    const session = useAskStore.getState().session
    expect(session?.event_seq).toBe(3)
    expect(session?.active_turn_id).toBeNull()
    expect(session?.messages).toHaveLength(2)
    expect(session?.messages[1].status).toBe('completed')
  })

  it('applies ask_assistant_error and ask_session_reset', () => {
    useAskStore.setState({
      session: makeSession({
        active_turn_id: 'turn_1',
        messages: [
          {
            message_id: 'msg_assistant',
            role: 'assistant',
            content: 'partial',
            status: 'streaming',
            created_at: '2026-03-10T00:00:00Z',
            updated_at: '2026-03-10T00:00:01Z',
            error: null,
          },
        ],
      }),
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_assistant_error',
      event_seq: 4,
      message_id: 'msg_assistant',
      content: 'partial',
      updated_at: '2026-03-10T00:00:02Z',
      error: 'boom',
    })

    expect(useAskStore.getState().session?.active_turn_id).toBeNull()
    expect(useAskStore.getState().session?.messages[0].status).toBe('error')

    useAskStore.getState().applyAskEvent({
      type: 'ask_session_reset',
      event_seq: 5,
      session: makeSession({ event_seq: 5 }),
    })

    expect(useAskStore.getState().session?.messages).toHaveLength(0)
    expect(useAskStore.getState().session?.delta_context_packets).toHaveLength(0)
  })

  it('ignores stale ask events by event_seq', () => {
    useAskStore.setState({
      session: makeSession({
        event_seq: 5,
        delta_context_packets: [makePacket({ status: 'approved' })],
      }),
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_packet_status_changed',
      event_seq: 4,
      packet: makePacket({ status: 'merged' }),
    })

    expect(useAskStore.getState().session?.event_seq).toBe(5)
    expect(useAskStore.getState().session?.delta_context_packets[0].status).toBe('approved')
  })

  it('applies ask_delta_context_suggested', () => {
    useAskStore.setState({ session: makeSession() })

    useAskStore.getState().applyAskEvent({
      type: 'ask_delta_context_suggested',
      event_seq: 1,
      packet: makePacket(),
    })

    expect(useAskStore.getState().session?.delta_context_packets).toHaveLength(1)
  })

  it('applies ask_packet_status_changed', () => {
    useAskStore.setState({
      session: makeSession({
        event_seq: 1,
        delta_context_packets: [makePacket()],
      }),
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_packet_status_changed',
      event_seq: 2,
      packet: makePacket({ status: 'approved' }),
    })

    expect(useAskStore.getState().session?.delta_context_packets[0].status).toBe('approved')
  })

  it('upserts packets by packet_id', () => {
    useAskStore.setState({
      session: makeSession({
        delta_context_packets: [makePacket({ packet_id: 'packet-1', status: 'pending' })],
      }),
    })

    useAskStore.getState().applyAskEvent({
      type: 'ask_packet_status_changed',
      event_seq: 1,
      packet: makePacket({ packet_id: 'packet-1', status: 'approved' }),
    })
    useAskStore.getState().applyAskEvent({
      type: 'ask_delta_context_suggested',
      event_seq: 2,
      packet: makePacket({ packet_id: 'packet-2', summary: 'Second packet' }),
    })

    expect(useAskStore.getState().session?.delta_context_packets).toHaveLength(2)
    expect(useAskStore.getState().session?.delta_context_packets[0].status).toBe('approved')
  })

  it('local approvePacket upserts returned packet without changing event_seq', async () => {
    apiMock.approveAskPacket.mockResolvedValue({
      packet: makePacket({ packet_id: 'packet-1', status: 'approved' }),
    })
    useAskStore.setState({
      session: makeSession({
        event_seq: 7,
        delta_context_packets: [makePacket({ packet_id: 'packet-1', status: 'pending' })],
      }),
    })

    await useAskStore.getState().approvePacket('project-1', 'node-1', 'packet-1')

    expect(useAskStore.getState().session?.event_seq).toBe(7)
    expect(useAskStore.getState().session?.delta_context_packets[0].status).toBe('approved')
  })

  it('local mergePacket upserts returned packet without changing event_seq', async () => {
    apiMock.mergeAskPacket.mockResolvedValue({
      packet: makePacket({
        packet_id: 'packet-1',
        status: 'merged',
        merged_at: '2026-03-10T00:00:03Z',
        merged_planning_turn_id: 'mergeturn_1',
      }),
    })
    useAskStore.setState({
      session: makeSession({
        event_seq: 9,
        delta_context_packets: [makePacket({ packet_id: 'packet-1', status: 'approved' })],
      }),
    })

    await useAskStore.getState().mergePacket('project-1', 'node-1', 'packet-1')

    expect(useAskStore.getState().session?.event_seq).toBe(9)
    expect(useAskStore.getState().session?.delta_context_packets[0].status).toBe('merged')
  })
})
