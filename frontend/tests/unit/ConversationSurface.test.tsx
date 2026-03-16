import type { ComponentProps } from 'react'

import { render, screen } from '@testing-library/react'
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

  it('preserves spacing and ignores unsupported parts inline while building text', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'streaming',
          parts: [
            makePart({ part_id: 'part_1', status: 'streaming', payload: { text: 'Hello ' } }),
            makePart({
              part_id: 'part_2',
              part_type: 'reasoning',
              order: 1,
              payload: { summary: 'internal' },
            }),
            makePart({
              part_id: 'part_3',
              status: 'streaming',
              order: 2,
              payload: { content: ' there' },
            }),
          ],
        }),
      ]),
    )

    expect(model?.messages[0]).toMatchObject({
      text: 'Hello  there',
      unsupportedPartTypes: ['reasoning'],
      isStreaming: true,
    })
  })

  it('builds unique stable unsupported fallback types and typing state', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'streaming',
          parts: [
            makePart({ part_id: 'part_1', part_type: 'reasoning', payload: { text: 'hidden' } }),
            makePart({ part_id: 'part_2', part_type: 'tool_call', order: 1, payload: { name: 'grep' } }),
            makePart({ part_id: 'part_3', part_type: 'reasoning', order: 2, payload: { text: 'duplicate' } }),
          ],
        }),
      ]),
    )

    expect(model?.messages[0]).toMatchObject({
      unsupportedPartTypes: ['reasoning', 'tool_call'],
      showTyping: true,
    })
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

  it('renders partial streaming assistant text in place', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'streaming',
          parts: [makePart({ status: 'streaming', payload: { text: 'Streaming in place' } })],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Streaming in place')).toBeInTheDocument()
    expect(screen.getByText('streaming')).toBeInTheDocument()
  })

  it('renders loading state only when there are no messages yet', () => {
    renderSurface(null, { isLoading: true })

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('No messages yet')).not.toBeInTheDocument()
  })

  it('renders empty state when not loading and there are no messages', () => {
    renderSurface({ messages: [] })

    expect(screen.getByText('No messages yet')).toBeInTheDocument()
    expect(screen.getByText('Start when you are ready.')).toBeInTheDocument()
  })

  it('renders a non-fatal surface error banner without hiding transcript content', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([makeMessage({ parts: [makePart({ payload: { text: 'Still visible' } })] })]),
    )

    renderSurface(model, { errorMessage: 'Connection dropped' })

    expect(screen.getByRole('alert')).toHaveTextContent('Connection dropped')
    expect(screen.getByText('Still visible')).toBeInTheDocument()
  })

  it('renders text and message-level error together', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          status: 'error',
          error: 'Tool failed',
          parts: [makePart({ payload: { text: 'Partial answer' } })],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Partial answer')).toBeInTheDocument()
    expect(screen.getByText('Tool failed')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
  })

  it('degrades unsupported-only messages to a deterministic fallback', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          role: 'user',
          parts: [
            makePart({ part_id: 'part_reasoning', part_type: 'reasoning', payload: { text: 'internal' } }),
            makePart({ part_id: 'part_tool', part_type: 'tool_call', order: 1, payload: { command: 'git status' } }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Unsupported content: reasoning, tool_call')).toBeInTheDocument()
  })

  it('renders supported text only when supported and unsupported parts are mixed', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          parts: [
            makePart({ part_id: 'part_text_1', payload: { text: 'Hello ' } }),
            makePart({ part_id: 'part_reasoning', part_type: 'reasoning', order: 1, payload: { text: 'hidden' } }),
            makePart({ part_id: 'part_text_2', order: 2, payload: { text: 'there' } }),
          ],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Hello there')).toBeInTheDocument()
    expect(screen.queryByText(/Unsupported content:/)).not.toBeInTheDocument()
  })

  it('renders system, tool, and unknown roles safely with neutral treatment', () => {
    const model = buildConversationRenderModel(
      makeSnapshot([
        makeMessage({
          message_id: 'msg_system',
          role: 'system',
          parts: [makePart({ part_id: 'part_system', part_type: 'reasoning', payload: { text: 'system fallback' } })],
        }),
        makeMessage({
          message_id: 'msg_tool',
          role: 'tool',
          parts: [makePart({ part_id: 'part_tool', part_type: 'tool_result', payload: { output: 'tool fallback' } })],
        }),
        makeMessage({
          message_id: 'msg_unknown',
          role: 'moderator' as unknown as ConversationSnapshot['messages'][number]['role'],
          parts: [makePart({ part_id: 'part_unknown', payload: { text: 'unexpected' } })],
        }),
      ]),
    )

    renderSurface(model)

    expect(screen.getByText('Unsupported content: reasoning')).toBeInTheDocument()
    expect(screen.getByText('Unsupported content: tool_result')).toBeInTheDocument()
    expect(screen.getByText('Unsupported content: assistant_text')).toBeInTheDocument()
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

  it('suppresses the composer when showComposer is false even if handlers exist', () => {
    renderSurface(
      { messages: [] },
      {
        showComposer: false,
        composerValue: 'Draft',
        onComposerValueChange: vi.fn(),
        onComposerSubmit: vi.fn(),
      },
    )

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
  })

  it('does not render an unusable composer when handlers are missing', () => {
    renderSurface(
      { messages: [] },
      {
        showComposer: true,
        composerValue: 'Draft',
      },
    )

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
  })
})
