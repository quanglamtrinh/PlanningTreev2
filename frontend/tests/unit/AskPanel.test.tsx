import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeRecord } from '../../src/api/types'
import { AskPanel } from '../../src/features/breadcrumb/AskPanel'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useAskStore } from '../../src/stores/ask-store'
import { useConversationStore } from '../../src/stores/conversation-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeNode(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    node_id: 'node-1',
    parent_id: null,
    child_ids: [],
    title: 'Ask Node',
    description: 'Clarify the ask host',
    status: 'draft',
    phase: 'planning',
    node_kind: 'original',
    planning_mode: null,
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    split_metadata: null,
    chat_session_id: null,
    has_planning_thread: true,
    has_execution_thread: false,
    planning_thread_status: 'idle',
    execution_thread_status: null,
    has_ask_thread: true,
    ask_thread_status: 'active',
    is_superseded: false,
    created_at: '2026-03-15T00:00:00Z',
    ...overrides,
  }
}

function makeConversationSnapshot(
  overrides: Partial<ConversationSnapshot> = {},
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_ask_1',
      project_id: 'project-1',
      node_id: 'node-1',
      thread_type: 'ask',
      app_server_thread_id: null,
      current_runtime_mode: 'ask',
      status: 'completed',
      active_stream_id: null,
      event_seq: 1,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:01Z',
      ...recordOverrides,
    },
    messages: [],
    ...overrides,
  }
}

function makeConversationSnapshotWithAssistantText(text: string): ConversationSnapshot {
  return makeConversationSnapshot({
    messages: [
      {
        message_id: 'msg_assistant_1',
        conversation_id: 'conv_ask_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'ask',
        status: 'completed',
        created_at: '2026-03-15T00:00:01Z',
        updated_at: '2026-03-15T00:00:01Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'part_assistant_1',
            part_type: 'assistant_text',
            status: 'completed',
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:01Z',
            updated_at: '2026-03-15T00:00:01Z',
            payload: { text },
          },
        ],
      },
    ],
  })
}

function AskConversationHarness({
  conversationId,
  bootstrapStatus = 'idle',
  bootstrapError = null,
  send = vi.fn(async () => undefined),
  refresh = vi.fn(),
}: {
  conversationId: string | null
  bootstrapStatus?: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError?: string | null
  send?: (content: string) => Promise<unknown>
  refresh?: () => void
}) {
  const conversation = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId] ?? null : null,
  )

  return (
    <AskPanel
      node={makeNode()}
      projectId="project-1"
      askConversation={{
        conversationId,
        conversation,
        bootstrapStatus,
        bootstrapError,
        send,
        refresh,
      }}
    />
  )
}

describe('AskPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAskStore.setState(useAskStore.getInitialState())
    useConversationStore.setState(useConversationStore.getInitialState())
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship phase 4.1',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-15T00:00:00Z',
          updated_at: '2026-03-15T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'node-1',
          active_node_id: 'node-1',
          node_registry: [makeNode()],
        },
        updated_at: '2026-03-15T00:00:00Z',
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows v2 loading without any legacy transcript fallback', () => {
    render(
      <AskConversationHarness
        conversationId={null}
        bootstrapStatus="loading_snapshot"
      />,
    )

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()
  })

  it('renders the ask-v2 branch and preserved packet sidecar together', () => {
    const snapshot = makeConversationSnapshotWithAssistantText('Ask v2 transcript')
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'node-1',
        eventSeq: 1,
        packetList: [
          {
            packet_id: 'packet_1',
            node_id: 'node-1',
            created_at: '2026-03-15T00:00:00Z',
            source_message_ids: [],
            summary: 'Scope note',
            context_text: 'Keep wrapper-owned sidecar.',
            status: 'pending',
            status_reason: null,
            merged_at: null,
            merged_planning_turn_id: null,
            suggested_by: 'agent',
          },
        ],
      },
    })

    render(<AskConversationHarness conversationId={conversationId} />)

    expect(screen.getByText('Ask v2 transcript')).toBeInTheDocument()
    expect(screen.getByText('Delta Context Packets')).toBeInTheDocument()
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()
  })

  it('shows bootstrap errors without falling back to a legacy transcript', () => {
    render(
      <AskConversationHarness
        conversationId={null}
        bootstrapStatus="error"
        bootstrapError="ask v2 bootstrap failed"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('ask v2 bootstrap failed')
    expect(screen.queryByText('Legacy ask transcript')).not.toBeInTheDocument()
  })

  it('sends through ask v2 and clears the keyed composer draft after success', async () => {
    const snapshot = makeConversationSnapshot()
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')
    useConversationStore.getState().setComposerDraft(conversationId, 'Clarify the plan')
    const send = vi.fn(async () => ({ status: 'accepted' }))

    render(<AskConversationHarness conversationId={conversationId} send={send} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Clarify the plan' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(send).toHaveBeenCalledWith('Clarify the plan')
    })
    expect(
      useConversationStore.getState().conversationsById[conversationId]?.composerDraft,
    ).toBe('')
  })
})
