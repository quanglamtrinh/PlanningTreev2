import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { NodeDocuments } from '../../src/api/types'
import { PlanningPanel } from '../../src/features/breadcrumb/PlanningPanel'
import type { ConversationSnapshot } from '../../src/features/conversation/types'
import { useConversationStore } from '../../src/stores/conversation-store'

const node = {
  node_id: 'child-1',
  parent_id: 'root',
  child_ids: [],
  title: 'Child',
  description: 'Child description',
  status: 'ready' as const,
  phase: 'planning' as const,
  planning_mode: null,
  depth: 1,
  display_order: 0,
  hierarchical_number: '1.1',
  split_metadata: null,
  chat_session_id: null,
  has_ask_thread: false,
  ask_thread_status: null,
  has_planning_thread: true,
  has_execution_thread: false,
  planning_thread_status: 'idle' as const,
  execution_thread_status: null,
  is_superseded: false,
  created_at: '2026-03-07T10:05:00Z',
}

const documents: NodeDocuments = {
  task: { title: 'Alpha', purpose: 'Ship phase 6.3', responsibility: '' },
  brief: null,
  briefing: null,
  spec: null,
  state: null,
  plan: null,
}

function makePlanningConversationSnapshot(
  text: string,
  recordOverrides: Partial<ConversationSnapshot['record']> = {},
): ConversationSnapshot {
  return {
    record: {
      conversation_id: 'conv_plan_1',
      project_id: 'project-1',
      node_id: 'child-1',
      thread_type: 'planning',
      app_server_thread_id: null,
      current_runtime_mode: 'planning',
      status: 'completed',
      active_stream_id: null,
      event_seq: 5,
      created_at: '2026-03-15T00:00:00Z',
      updated_at: '2026-03-15T00:00:03Z',
      ...recordOverrides,
    },
    messages: [
      {
        message_id: 'planning_msg:turn_1:assistant',
        conversation_id: 'conv_plan_1',
        turn_id: 'turn_1',
        role: 'assistant',
        runtime_mode: 'planning',
        status: 'completed',
        created_at: '2026-03-15T00:00:03Z',
        updated_at: '2026-03-15T00:00:03Z',
        lineage: {},
        usage: null,
        error: null,
        parts: [
          {
            part_id: 'planning_part:turn_1:assistant_text',
            part_type: 'assistant_text',
            status: 'completed',
            order: 0,
            item_key: null,
            created_at: '2026-03-15T00:00:03Z',
            updated_at: '2026-03-15T00:00:03Z',
            payload: { text },
          },
        ],
      },
    ],
  }
}

function PlanningConversationHarness({
  conversationId,
  bootstrapStatus = 'idle',
  bootstrapError = null,
}: {
  conversationId: string | null
  bootstrapStatus?: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError?: string | null
}) {
  const conversation = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId] ?? null : null,
  )

  return (
    <PlanningPanel
      node={node}
      documents={documents}
      planningConversation={{
        conversationId,
        conversation,
        bootstrapStatus,
        bootstrapError,
      }}
    />
  )
}

describe('PlanningPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState(useConversationStore.getInitialState())
  })

  it('renders the planning-v2 branch through the shared surface', () => {
    const snapshot = makePlanningConversationSnapshot('Planning v2 transcript')
    const conversationId = useConversationStore.getState().ensureConversation(snapshot)
    useConversationStore.getState().hydrateConversation(snapshot)
    useConversationStore.getState().setConnectionStatus(conversationId, 'connected')

    render(<PlanningConversationHarness conversationId={conversationId} />)

    expect(screen.getByText('Planning v2 transcript')).toBeInTheDocument()
    expect(screen.getByText('connected')).toBeInTheDocument()
    expect(screen.queryByText('Inherited from 1 Root')).not.toBeInTheDocument()
  })

  it('shows planning-v2 loading without any legacy planning fallback', () => {
    render(
      <PlanningConversationHarness
        conversationId={null}
        bootstrapStatus="loading_snapshot"
      />,
    )

    expect(screen.getByText('Loading conversation...')).toBeInTheDocument()
    expect(screen.queryByText('Inherited from 1 Root')).not.toBeInTheDocument()
  })

  it('shows planning-v2 error without showing a legacy transcript', () => {
    render(
      <PlanningConversationHarness
        conversationId={null}
        bootstrapStatus="error"
        bootstrapError="planning v2 bootstrap failed"
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('planning v2 bootstrap failed')
    expect(screen.queryByText('Inherited from 1 Root')).not.toBeInTheDocument()
  })

  it('keeps split actions visible on the v2 host path', () => {
    render(<PlanningConversationHarness conversationId={null} />)

    expect(screen.getByRole('button', { name: 'Walking Skeleton' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Slice' })).toBeInTheDocument()
  })
})
