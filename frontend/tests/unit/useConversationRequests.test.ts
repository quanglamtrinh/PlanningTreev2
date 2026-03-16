import { describe, expect, it } from 'vitest'

import { deriveConversationRequests } from '../../src/features/conversation/hooks/useConversationRequests'
import type { ConversationSnapshot } from '../../src/features/conversation/types'

function makeSnapshot(messages: ConversationSnapshot['messages']): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_requests_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'active',
      active_stream_id: 'stream_1',
      event_seq: 5,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:05Z',
    },
    messages,
  }
}

describe('deriveConversationRequests', () => {
  it('selects the latest unresolved request in normalized durable order', () => {
    const snapshot = makeSnapshot([
      {
        message_id: 'msg_req_old',
        conversation_id: 'conv_requests_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'pending',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_req_old',
            part_type: 'user_input_request',
            status: 'pending',
            order: 0,
            item_key: 'req_old',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: {
              request_id: 'req_old',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Old request',
              questions: [],
            },
          },
        ],
      },
      {
        message_id: 'msg_req_latest',
        conversation_id: 'conv_requests_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'pending',
        created_at: '2026-03-15T00:00:02Z',
        updated_at: '2026-03-15T00:00:02Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_req_latest',
            part_type: 'user_input_request',
            status: 'pending',
            order: 0,
            item_key: 'req_latest',
            created_at: '2026-03-15T00:00:02Z',
            updated_at: '2026-03-15T00:00:02Z',
            payload: {
              request_id: 'req_latest',
              request_kind: 'user_input',
              resolution_state: 'pending',
              title: 'Latest request',
              questions: [],
            },
          },
        ],
      },
    ])

    const derived = deriveConversationRequests(snapshot)

    expect(derived.pendingRequestCount).toBe(2)
    expect(derived.activeRequest?.requestId).toBe('req_latest')
    expect(derived.activeRequest?.title).toBe('Latest request')
  })

  it('ignores resolved requests when determining the active visible request', () => {
    const snapshot = makeSnapshot([
      {
        message_id: 'msg_req_old',
        conversation_id: 'conv_requests_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'completed',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_req_old',
            part_type: 'user_input_request',
            status: 'completed',
            order: 0,
            item_key: 'req_old',
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: {
              request_id: 'req_old',
              request_kind: 'user_input',
              resolution_state: 'resolved',
              title: 'Old request',
              questions: [],
            },
          },
        ],
      },
      {
        message_id: 'msg_req_latest',
        conversation_id: 'conv_requests_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'pending',
        created_at: '2026-03-15T00:00:02Z',
        updated_at: '2026-03-15T00:00:02Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_req_latest',
            part_type: 'approval_request',
            status: 'pending',
            order: 0,
            item_key: 'req_latest',
            created_at: '2026-03-15T00:00:02Z',
            updated_at: '2026-03-15T00:00:02Z',
            payload: {
              request_id: 'req_latest',
              request_kind: 'approval',
              resolution_state: 'pending',
              title: 'Latest approval',
            },
          },
        ],
      },
    ])

    const derived = deriveConversationRequests(snapshot)

    expect(derived.pendingRequestCount).toBe(1)
    expect(derived.activeRequest?.requestId).toBe('req_latest')
    expect(derived.activeRequest?.requestKind).toBe('approval')
  })
})
