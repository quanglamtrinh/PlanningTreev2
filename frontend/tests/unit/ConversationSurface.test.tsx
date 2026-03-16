import type { ComponentProps } from 'react'

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ConversationSurface } from '../../src/features/conversation/components/ConversationSurface'
import {
  buildConversationRenderModel,
  type ConversationRenderModel,
} from '../../src/features/conversation/model/buildConversationRenderModel'
import type { ConversationSnapshot } from '../../src/features/conversation/types'

function makeSnapshot(messages: ConversationSnapshot['messages']): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_surface_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'execution',
      app_server_thread_id: null,
      current_runtime_mode: 'execute',
      status: 'active',
      active_stream_id: 'stream_1',
      event_seq: 3,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:03Z',
    },
    messages,
  }
}

function makeMessage(
  overrides: Partial<ConversationSnapshot['messages'][number]>,
): ConversationSnapshot['messages'][number] {
  return {
    message_id: 'msg_1',
    conversation_id: 'conv_surface_1',
    turn_id: 'turn_1',
    role: 'assistant',
    runtime_mode: 'execute',
    status: 'completed',
    created_at: '2026-03-15T00:00:01Z',
    updated_at: '2026-03-15T00:00:01Z',
    lineage: {},
    usage: null,
    error: null,
    parts: [],
    ...overrides,
  }
}

function makePart(
  overrides: Partial<ConversationSnapshot['messages'][number]['parts'][number]>,
): ConversationSnapshot['messages'][number]['parts'][number] {
  return {
    part_id: 'part_1',
    part_type: 'assistant_text',
    status: 'completed',
    order: 0,
    item_key: null,
    created_at: '2026-03-15T00:00:01Z',
    updated_at: '2026-03-15T00:00:01Z',
    payload: {},
    ...overrides,
  }
}

function renderSurface(
  model: ConversationRenderModel | null,
  overrides: Partial<ComponentProps<typeof ConversationSurface>> = {},
) {
  return render(
    <ConversationSurface
      model={model}
      connectionState="connected"
      isLoading={false}
      errorMessage={null}
      emptyTitle="No messages yet"
      emptyHint="Start when you are ready."
      {...overrides}
    />,
  )
}

describe('buildConversationRenderModel', () => {
  it('preserves exact message order from the snapshot', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          message_id: 'msg_b',
          parts: [makePart({ part_id: 'part_b', payload: { text: 'Second' } })],
        }),
        makeMessage({
          message_id: 'msg_a',
          role: 'user',
          parts: [makePart({ part_id: 'part_a', part_type: 'user_text', payload: { text: 'First' } })],
        }),
      ]),
    )

    expect(model?.messages.map((message) => message.messageId)).toEqual(['msg_b', 'msg_a'])
  })

  it('builds ordered mixed render items for text and passive parts', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'streaming',
          parts: [
            makePart({ part_id: 'part_text_1', status: 'streaming', payload: { text: 'Hello ' } }),
            makePart({
              part_id: 'part_reasoning',
              part_type: 'reasoning',
              order: 1,
              payload: { summary: 'Inspecting repo state' },
            }),
            makePart({
              part_id: 'part_tool_call',
              part_type: 'tool_call',
              order: 2,
              payload: { tool_call_id: 'call_1', tool_name: 'grep', arguments: { pattern: 'TODO' } },
            }),
            makePart({ part_id: 'part_text_2', status: 'streaming', order: 3, payload: { content: 'there' } }),
          ],
        }),
      ]),
    )

    expect(model?.messages[0].items.map((item) => item.kind)).toEqual([
      'assistant_text',
      'reasoning',
      'tool_call',
      'assistant_text',
    ])
    expect(model?.messages[0].isStreaming).toBe(true)
  })

  it('distinguishes malformed known payloads from unsupported part types in the render model', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({ part_id: 'part_malformed', part_type: 'reasoning', payload: {} }),
            makePart({ part_id: 'part_unsupported', part_type: 'status_block', order: 1, payload: {} }),
          ],
        }),
      ]),
    )

    expect(model?.messages[0].items).toMatchObject([
      { kind: 'unsupported', reason: 'malformed_payload', partType: 'reasoning' },
      { kind: 'unsupported', reason: 'unsupported_part_type', partType: 'status_block' },
    ])
  })

  it('builds dedicated render items for interactive request and response parts', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({
              part_id: 'part_approval',
              part_type: 'approval_request',
              payload: {
                request_id: 'req_approval_1',
                title: 'Approve execution',
                prompt: 'Approve the workspace write step.',
                resolution_state: 'pending',
              },
            }),
            makePart({
              part_id: 'part_input_request',
              part_type: 'user_input_request',
              order: 1,
              payload: {
                request_id: 'req_input_1',
                title: 'Need runtime input',
                prompt: 'Choose a direction.',
                resolution_state: 'resolved',
                questions: [
                  {
                    id: 'brand_direction',
                    header: 'Brand direction',
                    question: 'What visual direction should we use?',
                    options: [{ label: 'Editorial' }, { label: 'Playful' }],
                  },
                ],
              },
            }),
          ],
        }),
        makeMessage({
          message_id: 'msg_user_response',
          role: 'user',
          parts: [
            makePart({
              part_id: 'part_input_response',
              part_type: 'user_input_response',
              payload: {
                request_id: 'req_input_1',
                title: 'Input submitted',
                text: 'Brand direction\nEditorial',
                answers: {
                  brand_direction: {
                    answers: ['Editorial'],
                  },
                },
              },
            }),
          ],
        }),
      ]),
    )

    expect(model?.messages[0].items.map((item) => item.kind)).toEqual([
      'approval_request',
      'user_input_request',
    ])
    expect(model?.messages[1].items.map((item) => item.kind)).toEqual(['user_input_response'])
  })
})

describe('ConversationSurface', () => {
  it('renders user and assistant text messages', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          message_id: 'msg_user',
          role: 'user',
          parts: [makePart({ part_id: 'part_user', part_type: 'user_text', payload: { text: 'Ship the flow' } })],
        }),
        makeMessage({
          message_id: 'msg_assistant',
          parts: [makePart({ part_id: 'part_assistant', payload: { text: 'On it.' } })],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Ship the flow')).toBeInTheDocument()
    expect(screen.getByText('On it.')).toBeInTheDocument()
  })

  it('renders typing indicator for an empty streaming assistant message', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'streaming',
          parts: [makePart({ status: 'streaming', payload: { text: '' } })],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByLabelText('Streaming response')).toBeInTheDocument()
    expect(screen.getByText('streaming')).toBeInTheDocument()
  })

  it('renders structured tool_call content instead of degrading it to unsupported fallback', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({ payload: { text: 'Split completed. Created 2 child tasks.' } }),
            makePart({
              part_id: 'part_tool',
              part_type: 'tool_call',
              order: 1,
              payload: {
                tool_call_id: 'call_split_1',
                tool_name: 'emit_render_data',
                arguments: {
                  kind: 'split_result',
                  payload: {
                    subtasks: [
                      { order: 1, prompt: 'Setup repo', risk_reason: 'env', what_unblocks: 'coding' },
                    ],
                  },
                },
              },
            }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Split completed. Created 2 child tasks.')).toBeInTheDocument()
    expect(screen.getByText('Slice 1')).toBeInTheDocument()
    expect(screen.getByText('Setup repo')).toBeInTheDocument()
    expect(screen.queryByText(/Unsupported content:/)).not.toBeInTheDocument()
  })

  it('renders reasoning, tool_result, plan, diff, and file-change passive blocks', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({ part_id: 'part_reasoning', part_type: 'reasoning', payload: { summary: 'Thinking aloud' } }),
            makePart({
              part_id: 'part_tool_result',
              part_type: 'tool_result',
              order: 1,
              payload: { result_for_item_id: 'call_1', text: 'Found 2 matches.' },
            }),
            makePart({
              part_id: 'part_plan',
              part_type: 'plan_block',
              order: 2,
              payload: {
                plan_id: 'plan_1',
                title: 'Implementation plan',
                steps: [{ step_id: 'step_1', title: 'Wire reducer', status: 'completed' }],
              },
            }),
            makePart({
              part_id: 'part_step',
              part_type: 'plan_step_update',
              order: 3,
              payload: { step_id: 'step_1', title: 'Wire reducer', status: 'completed' },
            }),
            makePart({
              part_id: 'part_diff',
              part_type: 'diff_summary',
              order: 4,
              payload: { summary: 'Touched reducer and surface.', files: ['applyConversationEvent.ts'] },
            }),
            makePart({
              part_id: 'part_file',
              part_type: 'file_change_summary',
              order: 5,
              payload: { file_path: 'ConversationSurface.tsx', change_type: 'modified', summary: 'Added block rendering.' },
            }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Thinking aloud')).toBeInTheDocument()
    expect(screen.getByText('Found 2 matches.')).toBeInTheDocument()
    expect(screen.getByText('Implementation plan')).toBeInTheDocument()
    expect(screen.getAllByText('Wire reducer')).toHaveLength(2)
    expect(screen.getByText('Touched reducer and surface.')).toBeInTheDocument()
    expect(screen.getByText('ConversationSurface.tsx')).toBeInTheDocument()
    expect(screen.getByText('modified')).toBeInTheDocument()
  })

  it('renders deterministic fallback blocks for malformed passive payloads', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({ part_id: 'part_reasoning', part_type: 'reasoning', payload: {} }),
            makePart({ part_id: 'part_unknown', part_type: 'status_block', order: 1, payload: {} }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Unsupported content: reasoning')).toBeInTheDocument()
    expect(screen.getByText('Unsupported content: status_block')).toBeInTheDocument()
  })

  it('renders approval, runtime input request, and runtime input response blocks', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({
              part_id: 'part_approval',
              part_type: 'approval_request',
              payload: {
                request_id: 'req_approval_1',
                title: 'Approve execution',
                prompt: 'Approve the workspace write step.',
                resolution_state: 'pending',
              },
            }),
            makePart({
              part_id: 'part_input_request',
              part_type: 'user_input_request',
              order: 1,
              payload: {
                request_id: 'req_input_1',
                title: 'Need runtime input',
                prompt: 'Choose a direction.',
                resolution_state: 'resolved',
                questions: [
                  {
                    id: 'brand_direction',
                    header: 'Brand direction',
                    question: 'What visual direction should we use?',
                    options: [{ label: 'Editorial' }, { label: 'Playful' }],
                  },
                ],
              },
            }),
          ],
        }),
        makeMessage({
          message_id: 'msg_user_response',
          role: 'user',
          parts: [
            makePart({
              part_id: 'part_input_response',
              part_type: 'user_input_response',
              payload: {
                request_id: 'req_input_1',
                title: 'Input submitted',
                text: 'Brand direction\nEditorial',
                answers: {
                  brand_direction: {
                    answers: ['Editorial'],
                  },
                },
              },
            }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Approve execution')).toBeInTheDocument()
    expect(screen.getByText('Approve the workspace write step.')).toBeInTheDocument()
    expect(screen.getByText('Need runtime input')).toBeInTheDocument()
    expect(screen.getByText('What visual direction should we use?')).toBeInTheDocument()
    expect(screen.getByText('Options: Editorial, Playful')).toBeInTheDocument()
    expect(screen.getByText('Input submitted')).toBeInTheDocument()
    expect(screen.getByText('Brand direction')).toBeInTheDocument()
    expect(screen.getByText('Editorial')).toBeInTheDocument()
  })

  it('renders loading state only when there are no messages yet', () => {
    renderSurface(null, { isLoading: true })

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('No messages yet')).not.toBeInTheDocument()
  })

  it('renders a non-fatal surface error banner without hiding transcript content', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([makeMessage({ parts: [makePart({ payload: { text: 'Still visible' } })] })]),
    )

    renderSurface(model, { errorMessage: 'Connection dropped' })

    expect(screen.getByRole('alert')).toHaveTextContent('Connection dropped')
    expect(screen.getByText('Still visible')).toBeInTheDocument()
  })

  it('renders the composer only when requested and wired', () => {
    renderSurface(
      { messages: [] },
      {
        showComposer: true,
        composerValue: 'Draft',
        onComposerValueChange: vi.fn(),
        onComposerSubmit: vi.fn(),
      },
    )

    expect(screen.getByRole('textbox')).toHaveValue('Draft')
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('renders composer hint content and forwards composer keydown events', () => {
    const onComposerKeyDown = vi.fn()

    renderSurface(
      { messages: [] },
      {
        showComposer: true,
        composerValue: 'Draft',
        composerHint: (
          <>
            <kbd>Enter</kbd> to send
          </>
        ),
        onComposerValueChange: vi.fn(),
        onComposerSubmit: vi.fn(),
        onComposerKeyDown,
      },
    )

    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })

    expect(screen.getByText('to send')).toBeInTheDocument()
    expect(onComposerKeyDown).toHaveBeenCalled()
  })

  it('can hide the shared surface header when the host provides its own framing', () => {
    renderSurface(
      { messages: [] },
      {
        showHeader: false,
        contextLabel: '1 / Ask Node',
      },
    )

    expect(screen.queryByText('1 / Ask Node')).not.toBeInTheDocument()
    expect(screen.queryByText('connected')).not.toBeInTheDocument()
  })
})
