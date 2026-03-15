import { beforeEach, describe, expect, it } from 'vitest'

import type {
  ConversationEventEnvelope,
  ConversationSnapshot,
} from '../../src/features/conversation/types'
import { useConversationStore } from '../../src/stores/conversation-store'

function makeSnapshot(overrides: Partial<ConversationSnapshot> = {}): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'idle',
      active_stream_id: null,
      event_seq: 0,
      created_at: '2026-03-14T00:00:00Z',
      updated_at: '2026-03-14T00:00:00Z',
    },
    messages: [],
    ...overrides,
  }
}

describe('useConversationStore', () => {
  beforeEach(() => {
    useConversationStore.setState(useConversationStore.getInitialState())
  })

  it('indexes one canonical conversation id per scope', () => {
    const snapshot = makeSnapshot()

    const firstId = useConversationStore.getState().ensureConversation(snapshot)
    const secondId = useConversationStore.getState().ensureConversation(snapshot)

    expect(firstId).toBe('conv_1')
    expect(secondId).toBe('conv_1')
    expect(
      useConversationStore.getState().getConversationIdByScope({
        project_id: 'project-1',
        node_id: 'node-1',
        thread_type: 'execution',
      }),
    ).toBe('conv_1')
  })

  it('upserts parts deterministically by part id and order', () => {
    const snapshot = makeSnapshot({
      messages: [
        {
          message_id: 'msg_1',
          conversation_id: 'conv_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'execute',
          status: 'streaming',
          created_at: '2026-03-14T00:00:00Z',
          updated_at: '2026-03-14T00:00:00Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [],
        },
      ],
    })

    useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().upsertPart('conv_1', 'msg_1', {
      part_id: 'part_b',
      part_type: 'assistant_text',
      status: 'streaming',
      order: 2,
      item_key: null,
      created_at: '2026-03-14T00:00:01Z',
      updated_at: '2026-03-14T00:00:01Z',
      payload: { content: 'B' },
    })
    useConversationStore.getState().upsertPart('conv_1', 'msg_1', {
      part_id: 'part_a',
      part_type: 'reasoning',
      status: 'completed',
      order: 1,
      item_key: 'item-1',
      created_at: '2026-03-14T00:00:02Z',
      updated_at: '2026-03-14T00:00:02Z',
      payload: { summary: 'A' },
    })
    useConversationStore.getState().upsertPart('conv_1', 'msg_1', {
      part_id: 'part_b',
      part_type: 'assistant_text',
      status: 'completed',
      order: 2,
      item_key: null,
      created_at: '2026-03-14T00:00:01Z',
      updated_at: '2026-03-14T00:00:03Z',
      payload: { content: 'B2' },
    })

    const parts = useConversationStore.getState().conversationsById.conv_1.snapshot.messages[0].parts

    expect(parts).toHaveLength(2)
    expect(parts[0].part_id).toBe('part_a')
    expect(parts[1].payload).toEqual({ content: 'B2' })
  })

  it('applies execution conversation events with stable assistant placeholder updates', () => {
    useConversationStore.getState().ensureConversation(makeSnapshot())

    const userCreated: ConversationEventEnvelope = {
      event_type: 'message_created',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 1,
      created_at: '2026-03-14T00:00:01Z',
      turn_id: 'turn_1',
      message_id: 'msg_user',
      payload: {
        message: {
          message_id: 'msg_user',
          conversation_id: 'conv_1',
          turn_id: 'turn_1',
          role: 'user',
          runtime_mode: 'execute',
          status: 'completed',
          created_at: '2026-03-14T00:00:01Z',
          updated_at: '2026-03-14T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'part_user',
              part_type: 'user_text',
              status: 'completed',
              order: 0,
              item_key: null,
              created_at: '2026-03-14T00:00:01Z',
              updated_at: '2026-03-14T00:00:01Z',
              payload: { text: 'Ship it' },
            },
          ],
        },
      },
    }
    const assistantCreated: ConversationEventEnvelope = {
      event_type: 'message_created',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 2,
      created_at: '2026-03-14T00:00:02Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        message: {
          message_id: 'msg_assistant',
          conversation_id: 'conv_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'execute',
          status: 'pending',
          created_at: '2026-03-14T00:00:02Z',
          updated_at: '2026-03-14T00:00:02Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'part_assistant',
              part_type: 'assistant_text',
              status: 'pending',
              order: 0,
              item_key: null,
              created_at: '2026-03-14T00:00:02Z',
              updated_at: '2026-03-14T00:00:02Z',
              payload: { text: '' },
            },
          ],
        },
      },
    }

    useConversationStore.getState().applyEvent('conv_1', userCreated)
    useConversationStore.getState().applyEvent('conv_1', assistantCreated)
    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'assistant_text_delta',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 3,
      created_at: '2026-03-14T00:00:03Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      item_id: 'part_assistant',
      payload: {
        part_id: 'part_assistant',
        delta: 'Hel',
        status: 'streaming',
      },
    })
    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'assistant_text_final',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 4,
      created_at: '2026-03-14T00:00:04Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      item_id: 'part_assistant',
      payload: {
        part_id: 'part_assistant',
        text: 'Hello world',
        status: 'completed',
      },
    })
    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'completion_status',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 5,
      created_at: '2026-03-14T00:00:05Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        status: 'completed',
        finished_at: '2026-03-14T00:00:05Z',
      },
    })

    const conversation = useConversationStore.getState().conversationsById.conv_1
    const assistant = conversation.snapshot.messages.find(
      (message) => message.message_id === 'msg_assistant',
    )

    expect(conversation.snapshot.record.event_seq).toBe(5)
    expect(conversation.snapshot.record.status).toBe('completed')
    expect(conversation.snapshot.record.active_stream_id).toBeNull()
    expect(assistant?.status).toBe('completed')
    expect(assistant?.parts[0].part_id).toBe('part_assistant')
    expect(assistant?.parts[0].payload).toMatchObject({
      text: 'Hello world',
      content: 'Hello world',
    })
  })

  it('ignores stale execution conversation events', () => {
    useConversationStore.getState().ensureConversation(
      makeSnapshot({
        record: {
          ...makeSnapshot().record,
          event_seq: 4,
        },
      }),
    )

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'completion_status',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 4,
      created_at: '2026-03-14T00:00:05Z',
      payload: {
        status: 'error',
        finished_at: '2026-03-14T00:00:05Z',
        error: 'stale',
      },
    })

    const conversation = useConversationStore.getState().conversationsById.conv_1
    expect(conversation.snapshot.record.event_seq).toBe(4)
    expect(conversation.snapshot.record.status).toBe('idle')
  })

  it('enforces stream ownership and only lets message_created establish active_stream_id', () => {
    useConversationStore.getState().ensureConversation(makeSnapshot())

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'assistant_text_delta',
      conversation_id: 'conv_1',
      stream_id: 'stream_wrong',
      event_seq: 1,
      created_at: '2026-03-14T00:00:01Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      item_id: 'part_assistant',
      payload: {
        part_id: 'part_assistant',
        delta: 'ignored',
        status: 'streaming',
      },
    })

    let conversation = useConversationStore.getState().conversationsById.conv_1
    expect(conversation.snapshot.record.active_stream_id).toBeNull()
    expect(conversation.snapshot.record.event_seq).toBe(0)

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'message_created',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 1,
      created_at: '2026-03-14T00:00:01Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        message: {
          message_id: 'msg_assistant',
          conversation_id: 'conv_1',
          turn_id: 'turn_1',
          role: 'assistant',
          runtime_mode: 'execute',
          status: 'pending',
          created_at: '2026-03-14T00:00:01Z',
          updated_at: '2026-03-14T00:00:01Z',
          lineage: {},
          usage: null,
          error: null,
          parts: [
            {
              part_id: 'part_assistant',
              part_type: 'assistant_text',
              status: 'pending',
              order: 0,
              item_key: null,
              created_at: '2026-03-14T00:00:01Z',
              updated_at: '2026-03-14T00:00:01Z',
              payload: { text: '' },
            },
          ],
        },
      },
    })

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'assistant_text_delta',
      conversation_id: 'conv_1',
      stream_id: 'stream_2',
      event_seq: 2,
      created_at: '2026-03-14T00:00:02Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      item_id: 'part_assistant',
      payload: {
        part_id: 'part_assistant',
        delta: 'wrong stream',
        status: 'streaming',
      },
    })

    conversation = useConversationStore.getState().conversationsById.conv_1
    const assistant = conversation.snapshot.messages.find((message) => message.message_id === 'msg_assistant')

    expect(conversation.snapshot.record.active_stream_id).toBe('stream_1')
    expect(conversation.snapshot.record.event_seq).toBe(1)
    expect(assistant?.parts[0].payload).toMatchObject({ text: '' })
  })

  it('rejects missing and non-owning completion events', () => {
    useConversationStore.getState().ensureConversation(
      makeSnapshot({
        record: {
          ...makeSnapshot().record,
          active_stream_id: 'stream_1',
          event_seq: 2,
          status: 'active',
        },
        messages: [
          {
            message_id: 'msg_assistant',
            conversation_id: 'conv_1',
            turn_id: 'turn_1',
            role: 'assistant',
            runtime_mode: 'execute',
            status: 'streaming',
            created_at: '2026-03-14T00:00:01Z',
            updated_at: '2026-03-14T00:00:02Z',
            lineage: {},
            usage: null,
            error: null,
            parts: [
              {
                part_id: 'part_assistant',
                part_type: 'assistant_text',
                status: 'streaming',
                order: 0,
                item_key: null,
                created_at: '2026-03-14T00:00:01Z',
                updated_at: '2026-03-14T00:00:02Z',
                payload: { text: 'Hello' },
              },
            ],
          },
        ],
      }),
    )

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'completion_status',
      conversation_id: 'conv_1',
      stream_id: '',
      event_seq: 3,
      created_at: '2026-03-14T00:00:03Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        status: 'completed',
        finished_at: '2026-03-14T00:00:03Z',
      },
    })

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'completion_status',
      conversation_id: 'conv_1',
      stream_id: 'stream_2',
      event_seq: 4,
      created_at: '2026-03-14T00:00:04Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        status: 'completed',
        finished_at: '2026-03-14T00:00:04Z',
      },
    })

    useConversationStore.getState().applyEvent('conv_1', {
      event_type: 'completion_status',
      conversation_id: 'conv_1',
      stream_id: 'stream_1',
      event_seq: 5,
      created_at: '2026-03-14T00:00:05Z',
      turn_id: 'turn_1',
      message_id: 'msg_assistant',
      payload: {
        status: 'completed',
        finished_at: '2026-03-14T00:00:05Z',
      },
    })

    const conversation = useConversationStore.getState().conversationsById.conv_1

    expect(conversation.snapshot.record.event_seq).toBe(5)
    expect(conversation.snapshot.record.active_stream_id).toBeNull()
    expect(conversation.snapshot.record.status).toBe('completed')
  })
})
