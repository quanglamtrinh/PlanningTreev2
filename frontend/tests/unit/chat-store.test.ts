import { beforeEach, describe, expect, it } from 'vitest'

import type { ChatSession } from '../../src/api/types'
import { useChatStore } from '../../src/stores/chat-store'

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    project_id: 'project-1',
    node_id: 'node-1',
    thread_id: null,
    active_turn_id: null,
    event_seq: 0,
    config: {
      access_mode: 'project_write',
      cwd: 'C:/workspace/project',
      writable_roots: ['C:/workspace/project'],
      timeout_sec: 120,
    },
    messages: [],
    ...overrides,
  }
}

describe('chat-store', () => {
  beforeEach(() => {
    useChatStore.setState(useChatStore.getInitialState())
  })

  it('applies message, delta, and completion events to the current session', () => {
    useChatStore.setState({ session: makeSession() })

    useChatStore.getState().applyChatEvent({
      type: 'message_created',
      event_seq: 1,
      active_turn_id: 'turn_1',
      user_message: {
        message_id: 'msg_user',
        role: 'user',
        content: 'hello',
        status: 'completed',
        created_at: '2026-03-08T00:00:00Z',
        updated_at: '2026-03-08T00:00:00Z',
        error: null,
      },
      assistant_message: {
        message_id: 'msg_assistant',
        role: 'assistant',
        content: '',
        status: 'pending',
        created_at: '2026-03-08T00:00:00Z',
        updated_at: '2026-03-08T00:00:00Z',
        error: null,
      },
    })

    useChatStore.getState().applyChatEvent({
      type: 'assistant_delta',
      event_seq: 2,
      message_id: 'msg_assistant',
      delta: 'hel',
      content: 'hel',
      updated_at: '2026-03-08T00:00:01Z',
    })

    useChatStore.getState().applyChatEvent({
      type: 'assistant_completed',
      event_seq: 3,
      message_id: 'msg_assistant',
      content: 'hello world',
      updated_at: '2026-03-08T00:00:02Z',
    })

    const session = useChatStore.getState().session
    expect(session?.active_turn_id).toBeNull()
    expect(session?.event_seq).toBe(3)
    expect(session?.thread_id).toBeNull()
    expect(session?.messages).toHaveLength(2)
    expect(session?.messages[1].status).toBe('completed')
    expect(session?.messages[1].content).toBe('hello world')
  })

  it('applies assistant_error and session_reset events', () => {
    useChatStore.setState({
      session: makeSession({
        active_turn_id: 'turn_1',
        messages: [
          {
            message_id: 'msg_assistant',
            role: 'assistant',
            content: 'partial',
            status: 'streaming',
            created_at: '2026-03-08T00:00:00Z',
            updated_at: '2026-03-08T00:00:01Z',
            error: null,
          },
        ],
      }),
    })

    useChatStore.getState().applyChatEvent({
      type: 'assistant_error',
      event_seq: 4,
      message_id: 'msg_assistant',
      content: 'partial',
      updated_at: '2026-03-08T00:00:02Z',
      error: 'boom',
    })

    expect(useChatStore.getState().session?.active_turn_id).toBeNull()
    expect(useChatStore.getState().session?.messages[0].status).toBe('error')
    expect(useChatStore.getState().session?.messages[0].error).toBe('boom')

    useChatStore.getState().applyChatEvent({
      type: 'session_reset',
      event_seq: 5,
      session: makeSession({
        event_seq: 5,
        messages: [],
      }),
    })

    expect(useChatStore.getState().session?.messages).toHaveLength(0)
    expect(useChatStore.getState().session?.thread_id).toBeNull()
  })

  it('ignores stale events that arrive out of order', () => {
    useChatStore.setState({
      session: makeSession({
        event_seq: 3,
        messages: [
          {
            message_id: 'msg_assistant',
            role: 'assistant',
            content: 'hello',
            status: 'completed',
            created_at: '2026-03-08T00:00:00Z',
            updated_at: '2026-03-08T00:00:00Z',
            error: null,
          },
        ],
      }),
    })

    useChatStore.getState().applyChatEvent({
      type: 'assistant_error',
      event_seq: 2,
      message_id: 'msg_assistant',
      content: 'hello',
      updated_at: '2026-03-08T00:00:01Z',
      error: 'stale',
    })

    expect(useChatStore.getState().session?.event_seq).toBe(3)
    expect(useChatStore.getState().session?.messages[0].status).toBe('completed')
  })
})
