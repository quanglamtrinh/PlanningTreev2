import { describe, expect, it } from 'vitest'

import { deriveExecutionBusy } from '../../src/features/conversation/model/deriveExecutionBusy'
import type { ConversationSnapshot } from '../../src/features/conversation/types'

function makeSnapshot(
  overrides: Partial<ConversationSnapshot> = {},
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_exec_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'completed',
      active_stream_id: null,
      event_seq: 4,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
      ...recordOverrides,
    },
    messages: [],
    ...overrides,
  }
}

function makeAssistantMessage(
  overrides: Partial<ConversationSnapshot['messages'][number]> = {},
  partOverrides: Partial<ConversationSnapshot['messages'][number]['parts'][number]> = {},
) {
  return {
    message_id: 'msg_assistant_1',
    conversation_id: 'conv_exec_1',
    turn_id: 'turn_1',
    role: 'assistant' as const,
    runtime_mode: 'execute' as const,
    status: 'completed' as const,
    created_at: '2026-03-15T00:00:02Z',
    updated_at: '2026-03-15T00:00:02Z',
    lineage: {},
    usage: null,
    error: null,
    parts: [
      {
        part_id: 'part_assistant_1',
        part_type: 'assistant_text' as const,
        status: 'completed' as const,
        order: 0,
        item_key: null,
        created_at: '2026-03-15T00:00:02Z',
        updated_at: '2026-03-15T00:00:02Z',
        payload: { text: 'done' },
        ...partOverrides,
      },
    ],
    ...overrides,
  }
}

describe('deriveExecutionBusy', () => {
  it('returns true when an active stream id is present', () => {
    expect(deriveExecutionBusy(makeSnapshot({}, { active_stream_id: 'stream_live' }))).toBe(true)
  })

  it('returns true when the record status is active even without a stream id', () => {
    expect(deriveExecutionBusy(makeSnapshot({}, { status: 'active', active_stream_id: null }))).toBe(
      true,
    )
  })

  it('returns true when the latest assistant message is pending', () => {
    const snapshot = makeSnapshot({
      messages: [makeAssistantMessage({ status: 'pending' })],
    })

    expect(deriveExecutionBusy(snapshot)).toBe(true)
  })

  it('returns true when the latest assistant text part is streaming', () => {
    const snapshot = makeSnapshot({
      messages: [makeAssistantMessage({}, { status: 'streaming' })],
    })

    expect(deriveExecutionBusy(snapshot)).toBe(true)
  })

  it('returns false for interrupted state with message error once the latest assistant turn is terminal', () => {
    const snapshot = makeSnapshot(
      {
        messages: [
          makeAssistantMessage({
            status: 'interrupted',
            error: 'Execution conversation was interrupted before completion.',
          }, { status: 'interrupted' }),
        ],
      },
      { status: 'interrupted', active_stream_id: null },
    )

    expect(deriveExecutionBusy(snapshot)).toBe(false)
  })

  it('ignores stale historical pending assistant state when the latest assistant turn is terminal', () => {
    const snapshot = makeSnapshot({
      messages: [
        makeAssistantMessage(
          {
            message_id: 'msg_assistant_old',
            turn_id: 'turn_old',
            status: 'pending',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
          },
          {
            part_id: 'part_old',
            status: 'pending',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text: '' },
          },
        ),
        makeAssistantMessage({
          message_id: 'msg_assistant_new',
          turn_id: 'turn_new',
          created_at: '2026-03-15T00:00:02Z',
          updated_at: '2026-03-15T00:00:02Z',
        }),
      ],
    })

    expect(deriveExecutionBusy(snapshot)).toBe(false)
  })
})
