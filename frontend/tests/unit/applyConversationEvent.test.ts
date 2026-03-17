import { describe, expect, it, vi } from 'vitest'

import {
  applyConversationEvent,
  evaluateConversationEventAcceptance,
} from '../../src/features/conversation/model/applyConversationEvent'
import type { ConversationEventEnvelope, ConversationSnapshot } from '../../src/features/conversation/types'

function makeSnapshot(overrides: Partial<ConversationSnapshot> = {}): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'active',
      active_stream_id: 'stream_1',
      event_seq: 2,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:02Z',
    },
    messages: [
      {
        message_id: 'msg_assistant',
        conversation_id: 'conv_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'execute',
        status: 'streaming',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:02Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_text',
            part_type: 'assistant_text',
            status: 'streaming',
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:02Z',
            payload: { text: 'Working...' },
          },
        ],
      },
    ],
    ...overrides,
  }
}

function makeEvent(
  overrides: Partial<ConversationEventEnvelope>,
  payload: Record<string, unknown>,
): ConversationEventEnvelope {
  return {
    event_type: 'tool_call_start',
    conversation_id: 'conv_1',
    stream_id: 'stream_1',
    event_seq: 3,
    created_at: '2026-03-15T00:00:03Z',
    turn_id: 'turn_1',
    payload,
    ...overrides,
  }
}

describe('applyConversationEvent passive semantics', () => {
  it('marks gapful event sequences for recovery instead of local synthesis', () => {
    const acceptance = evaluateConversationEventAcceptance(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'assistant_text_delta',
          event_seq: 5,
          message_id: 'msg_assistant',
          item_id: 'part_text',
        },
        {
          part_id: 'part_text',
          delta: ' skipped',
          status: 'streaming',
        },
      ),
    )

    expect(acceptance).toEqual({
      decision: 'recover',
      reason: 'event_gap',
    })
  })

  it('resolves a target message by turn_id and a target part by semantic-specific tool_call_id', () => {
    const next = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'tool_call_start',
        },
        {
          tool_call_id: 'call_1',
          tool_name: 'emit_render_data',
          arguments: { kind: 'split_result', payload: { subtasks: [{ order: 1, prompt: 'Setup repo' }] } },
        },
      ),
    )

    const assistant = next.messages[0]

    expect(assistant.parts).toHaveLength(2)
    expect(assistant.parts[1]).toMatchObject({
      part_type: 'tool_call',
      item_key: 'call_1',
      part_id: 'msg_assistant:tool_call:call_1',
    })
    expect(next.record.event_seq).toBe(3)
  })

  it('updates plan_step_update in place by stable step_id without duplicating parts', () => {
    const initial = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'plan_step_status_change',
          event_seq: 3,
          created_at: '2026-03-15T00:00:03Z',
        },
        {
          step_id: 'step_1',
          title: 'Wire reducer',
          status: 'pending',
        },
      ),
    )

    const next = applyConversationEvent(
      initial,
      makeEvent(
        {
          event_type: 'plan_step_status_change',
          event_seq: 4,
          created_at: '2026-03-15T00:00:04Z',
        },
        {
          step_id: 'step_1',
          title: 'Wire reducer',
          status: 'completed',
          summary: 'Reducer parity is in place.',
        },
      ),
    )

    const planParts = next.messages[0].parts.filter((part) => part.part_type === 'plan_step_update')

    expect(planParts).toHaveLength(1)
    expect(planParts[0]).toMatchObject({
      item_key: 'step_1',
      payload: {
        step_id: 'step_1',
        status: 'completed',
        summary: 'Reducer parity is in place.',
      },
    })
  })

  it('ignores passive updates when deterministic message attachment cannot be resolved', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const next = applyConversationEvent(
      makeSnapshot({
        messages: [],
      }),
      makeEvent(
        {
          event_type: 'diff_summary',
        },
        {
          summary_id: 'diff_1',
          summary: 'Touched three files.',
        },
      ),
    )

    expect(next.messages).toEqual([])
    expect(next.record.event_seq).toBe(2)
    expect(warn).toHaveBeenCalledWith(
      '[conversation] dropped passive event',
      expect.objectContaining({
        reason: 'missing_assistant_target_for_turn',
        eventType: 'diff_summary',
      }),
    )
    warn.mockRestore()
  })

  it('rejects passive events that only match a non-assistant message for the same turn', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const next = applyConversationEvent(
      makeSnapshot({
        messages: [
          {
            ...makeSnapshot().messages[0],
            message_id: 'msg_user_only',
            role: 'user',
            parts: [
              {
                part_id: 'part_user',
                part_type: 'user_text',
                status: 'completed',
                order: 0,
                item_key: null,
                created_at: '2026-03-15T00:00:01Z',
                updated_at: '2026-03-15T00:00:01Z',
                payload: { text: 'hello' },
              },
            ],
          },
        ],
      }),
      makeEvent(
        {
          event_type: 'plan_block',
          message_id: undefined,
        },
        {
          turn_id: 'turn_1',
          plan_id: 'plan_1',
          text: 'Wire reducer first.',
        },
      ),
    )

    expect(next.messages[0].parts).toHaveLength(1)
    expect(warn).toHaveBeenCalledWith(
      '[conversation] dropped passive event',
      expect.objectContaining({
        reason: 'missing_assistant_target_for_turn',
        eventType: 'plan_block',
      }),
    )
    warn.mockRestore()
  })

  it('updates plan_block in place by stable plan_id without duplicating renderable parts', () => {
    const initial = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'plan_block',
          event_seq: 3,
          created_at: '2026-03-15T00:00:03Z',
        },
        {
          plan_id: 'plan_1',
          text: 'Draft plan',
          steps: [{ step_id: 'step_1', title: 'Wire reducer', status: 'pending' }],
        },
      ),
    )

    const next = applyConversationEvent(
      initial,
      makeEvent(
        {
          event_type: 'plan_block',
          event_seq: 4,
          created_at: '2026-03-15T00:00:04Z',
        },
        {
          plan_id: 'plan_1',
          text: 'Finalized plan',
          steps: [{ step_id: 'step_1', title: 'Wire reducer', status: 'completed' }],
        },
      ),
    )

    const planParts = next.messages[0].parts.filter((part) => part.part_type === 'plan_block')

    expect(planParts).toHaveLength(1)
    expect(planParts[0]).toMatchObject({
      item_key: 'plan_1',
      payload: {
        plan_id: 'plan_1',
        text: 'Finalized plan',
      },
    })
  })

  it('keeps tool_result association stable without depending on adjacency', () => {
    const withToolCall = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'tool_call_finish',
          event_seq: 3,
          message_id: 'msg_assistant',
          item_id: 'part_tool_call',
        },
        {
          part_id: 'part_tool_call',
          tool_call_id: 'call_1',
          tool_name: 'grep',
          arguments: { pattern: 'TODO' },
        },
      ),
    )

    const next = applyConversationEvent(
      withToolCall,
      makeEvent(
        {
          event_type: 'tool_result',
          event_seq: 4,
        },
        {
          result_for_item_id: 'part_tool_call',
          text: 'Found 2 matches.',
        },
      ),
    )

    const resultPart = next.messages[0].parts.find((part) => part.part_type === 'tool_result')
    expect(resultPart?.payload).toMatchObject({
      result_for_item_id: 'part_tool_call',
      text: 'Found 2 matches.',
    })
  })

  it('creates a user_input_request message from request_user_input and resolves it in place', () => {
    const requested = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'request_user_input',
          event_seq: 3,
        },
        {
          message: {
            message_id: 'msg_exec_request:req_1',
            conversation_id: 'conv_1',
            turn_id: 'turn_1',
            role: 'assistant',
            runtime_mode: 'execute',
            status: 'pending',
            created_at: '2026-03-15T00:00:03Z',
            updated_at: '2026-03-15T00:00:03Z',
            lineage: {},
            usage: null,
            error: null,
            parts: [
              {
                part_id: 'msg_exec_request:req_1:user_input_request',
                part_type: 'user_input_request',
                status: 'pending',
                order: 0,
                item_key: 'req_1',
                created_at: '2026-03-15T00:00:03Z',
                updated_at: '2026-03-15T00:00:03Z',
                payload: {
                  part_id: 'msg_exec_request:req_1:user_input_request',
                  request_id: 'req_1',
                  request_kind: 'user_input',
                  resolution_state: 'pending',
                  title: 'Runtime input needed',
                  questions: [
                    {
                      id: 'brand_direction',
                      header: 'Brand direction',
                      question: 'What visual direction should we use?',
                      options: [{ label: 'Editorial' }],
                    },
                  ],
                },
              },
            ],
          },
        },
      ),
    )

    const resolved = applyConversationEvent(
      requested,
      makeEvent(
        {
          event_type: 'request_resolved',
          event_seq: 4,
          message_id: 'msg_exec_request:req_1',
          item_id: 'msg_exec_request:req_1:user_input_request',
        },
        {
          request_id: 'req_1',
          request_kind: 'user_input',
          resolution_state: 'resolved',
          resolved_at: '2026-03-15T00:00:04Z',
        },
      ),
    )

    const requestMessage = resolved.messages.find((message) => message.message_id === 'msg_exec_request:req_1')
    expect(requestMessage?.parts[0]).toMatchObject({
      part_type: 'user_input_request',
      payload: {
        request_id: 'req_1',
        resolution_state: 'resolved',
      },
      status: 'completed',
    })
  })

  it('ignores request resolution events from a stale turn even when request ids match', () => {
    const requested = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'request_user_input',
          event_seq: 3,
        },
        {
          message: {
            message_id: 'msg_exec_request:req_1',
            conversation_id: 'conv_1',
            turn_id: 'turn_1',
            role: 'assistant',
            runtime_mode: 'execute',
            status: 'pending',
            created_at: '2026-03-15T00:00:03Z',
            updated_at: '2026-03-15T00:00:03Z',
            lineage: {},
            usage: null,
            error: null,
            parts: [
              {
                part_id: 'msg_exec_request:req_1:user_input_request',
                part_type: 'user_input_request',
                status: 'pending',
                order: 0,
                item_key: 'req_1',
                created_at: '2026-03-15T00:00:03Z',
                updated_at: '2026-03-15T00:00:03Z',
                payload: {
                  part_id: 'msg_exec_request:req_1:user_input_request',
                  request_id: 'req_1',
                  request_kind: 'user_input',
                  resolution_state: 'pending',
                  title: 'Runtime input needed',
                  questions: [],
                },
              },
            ],
          },
        },
      ),
    )

    const resolved = applyConversationEvent(
      requested,
      makeEvent(
        {
          event_type: 'request_resolved',
          event_seq: 4,
          turn_id: 'turn_2',
          message_id: 'msg_exec_request:req_1',
          item_id: 'msg_exec_request:req_1:user_input_request',
        },
        {
          request_id: 'req_1',
          request_kind: 'user_input',
          resolution_state: 'resolved',
          resolved_at: '2026-03-15T00:00:04Z',
        },
      ),
    )

    const requestMessage = resolved.messages.find((message) => message.message_id === 'msg_exec_request:req_1')
    expect(requestMessage?.parts[0]).toMatchObject({
      payload: {
        request_id: 'req_1',
        resolution_state: 'pending',
      },
      status: 'pending',
    })
    expect(resolved.record.event_seq).toBe(3)
  })

  it('creates a user_input_response message from user_input_resolved', () => {
    const next = applyConversationEvent(
      makeSnapshot(),
      makeEvent(
        {
          event_type: 'user_input_resolved',
          event_seq: 3,
        },
        {
          message: {
            message_id: 'msg_exec_request_response:req_1',
            conversation_id: 'conv_1',
            turn_id: 'turn_1',
            role: 'user',
            runtime_mode: 'execute',
            status: 'completed',
            created_at: '2026-03-15T00:00:03Z',
            updated_at: '2026-03-15T00:00:03Z',
            lineage: {},
            usage: null,
            error: null,
            parts: [
              {
                part_id: 'msg_exec_request_response:req_1:user_input_response',
                part_type: 'user_input_response',
                status: 'completed',
                order: 0,
                item_key: 'req_1',
                created_at: '2026-03-15T00:00:03Z',
                updated_at: '2026-03-15T00:00:03Z',
                payload: {
                  part_id: 'msg_exec_request_response:req_1:user_input_response',
                  request_id: 'req_1',
                  request_kind: 'user_input',
                  title: 'Input submitted',
                  text: 'Brand direction\nEditorial',
                  answers: {
                    brand_direction: {
                      answers: ['Editorial'],
                    },
                  },
                },
              },
            ],
          },
        },
      ),
    )

    const responseMessage = next.messages.find(
      (message) => message.message_id === 'msg_exec_request_response:req_1',
    )
    expect(responseMessage).toMatchObject({
      role: 'user',
      parts: [
        {
          part_type: 'user_input_response',
          payload: {
            request_id: 'req_1',
            title: 'Input submitted',
          },
        },
      ],
    })
  })
})
