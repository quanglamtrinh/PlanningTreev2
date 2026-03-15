import { beforeEach, describe, expect, it } from 'vitest'

import type { ConversationSnapshot } from '../../src/features/conversation/types'
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
})
