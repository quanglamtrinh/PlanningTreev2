import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, MockApiError, navigateMock } = vi.hoisted(() => ({
  MockApiError: class extends Error {
    status: number
    code: string | null
    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  },
  apiMock: {
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
    getReviewState: vi.fn().mockResolvedValue({
      checkpoints: [],
      rollup: {
        status: 'pending',
        summary: null,
        sha: null,
        accepted_at: null,
        draft: {
          summary: null,
          sha: null,
          generated_at: null,
        },
      },
      pending_siblings: [],
      sibling_manifest: [],
    }),
    getDetailState: vi.fn().mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      active_step: 'frame' as const,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    }),
    getSnapshot: vi.fn(),
    confirmFrame: vi.fn(),
    getClarify: vi.fn().mockResolvedValue({
      schema_version: 1,
      source_frame_revision: 0,
      confirmed_at: null,
      questions: [],
      updated_at: null,
    }),
    updateClarify: vi.fn(),
    confirmClarify: vi.fn(),
    confirmSpec: vi.fn(),
    finishTask: vi.fn(),
    getWorkflowStateV2: vi.fn(),
    finishTaskWorkflowV2: vi.fn(),
    generateFrame: vi.fn(),
    getFrameGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
    generateClarify: vi.fn(),
    getClarifyGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
    generateSpec: vi.fn(),
    getSpecGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
    splitNode: vi.fn(),
    getSplitStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: '2026-03-21T00:00:04Z',
      error: null,
    }),
    acceptRollupReview: vi.fn().mockResolvedValue({
      review_node_id: 'review-1',
      rollup_status: 'accepted',
      summary: 'Accepted rollup summary',
      sha: 'sha256:accepted',
    }),
  },
  navigateMock: vi.fn(),
}))

vi.mock('@uiw/react-codemirror', () => ({
  default: ({
    value,
    onChange,
    onBlur,
  }: {
    value: string
    onChange?: (value: string) => void
    onBlur?: () => void
  }) => (
    <textarea
      data-testid="mock-codemirror"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      onBlur={() => onBlur?.()}
    />
  ),
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  ApiError: MockApiError,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

import type { NodeRecord } from '../../src/api/types'
import { NodeDetailCard } from '../../src/features/node/NodeDetailCard'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useClarifyStore } from '../../src/stores/clarify-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeNode(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    node_id: 'root',
    parent_id: null,
    child_ids: [],
    title: 'Root',
    description: 'Root node',
    status: 'draft',
    node_kind: 'root',
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    is_superseded: false,
    created_at: '2026-03-21T00:00:00Z',
    workflow: {
      frame_confirmed: false,
      active_step: 'frame',
      spec_confirmed: false,
    },
    ...overrides,
  }
}

function makeReviewDetailState(overrides: Record<string, unknown> = {}) {
  return {
    node_id: 'review-1',
    workflow: null,
    frame_confirmed: false,
    frame_confirmed_revision: 0,
    frame_revision: 0,
    active_step: 'frame' as const,
    workflow_notice: null,
    generation_error: null,
    frame_needs_reconfirm: false,
    frame_read_only: true,
    clarify_read_only: true,
    clarify_confirmed: false,
    spec_read_only: true,
    spec_stale: false,
    spec_confirmed: false,
    execution_started: false,
    execution_completed: false,
    shaping_frozen: false,
    can_finish_task: false,
    can_accept_local_review: false,
    execution_status: null,
    audit_writable: false,
    package_audit_ready: false,
    review_status: 'pending' as const,
    ...overrides,
  }
}

describe('NodeDetailCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    sessionStorage.clear()
    useNodeDocumentStore.getState().reset()
    useDetailStateStore.getState().reset()
    useClarifyStore.getState().reset()
    useProjectStore.setState(useProjectStore.getInitialState())
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      active_step: 'frame' as const,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getClarify.mockResolvedValue({
      schema_version: 1,
      source_frame_revision: 0,
      confirmed_at: null,
      questions: [],
      updated_at: null,
    })
    apiMock.getClarifyGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getSpecGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getSplitStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      node_id: null,
      mode: null,
      started_at: null,
      completed_at: '2026-03-21T00:00:04Z',
      error: null,
    })
    apiMock.getReviewState.mockResolvedValue({
      checkpoints: [],
      rollup: {
        status: 'pending',
        summary: null,
        sha: null,
        accepted_at: null,
        draft: {
          summary: null,
          sha: null,
          generated_at: null,
        },
      },
      pending_siblings: [],
      sibling_manifest: [],
    })
    apiMock.acceptRollupReview.mockResolvedValue({
      review_node_id: 'review-1',
      rollup_status: 'accepted',
      summary: 'Accepted rollup summary',
      sha: 'sha256:accepted',
    })
    apiMock.finishTaskWorkflowV2.mockResolvedValue({
      accepted: true,
      workflowPhase: 'execution_running',
      threadId: 'thread-execution-1',
      executionRunId: 'run-1',
    })
    apiMock.getWorkflowStateV2.mockResolvedValue({
      nodeId: 'root',
      workflowPhase: 'execution_running',
      executionThreadId: 'thread-execution-1',
      auditLineageThreadId: 'thread-audit-lineage-1',
      reviewThreadId: null,
      activeExecutionRunId: 'run-1',
      latestExecutionRunId: 'run-1',
      activeReviewCycleId: null,
      latestReviewCycleId: null,
      currentExecutionDecision: null,
      currentAuditDecision: null,
      acceptedSha: null,
      runtimeBlock: null,
      canSendExecutionMessage: false,
      canReviewInAudit: false,
      canImproveInExecution: false,
      canMarkDoneFromExecution: false,
      canMarkDoneFromAudit: false,
    })
  })

  it('loads frame.md on the default Frame tab', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    })
    expect(screen.getByDisplayValue('# Frame')).toBeInTheDocument()
  })

  it('lazy-loads spec.md when switching to the Spec tab', async () => {
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    // Wait for detail state to load so Spec tab is unlocked
    const specButton = await screen.findByRole('button', { name: 'Spec' })
    fireEvent.click(specButton)

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'spec')
    })
    expect(screen.getByDisplayValue('# Spec')).toBeInTheDocument()
  })

  it('keeps coarse node status visible even when execution lifecycle is completed', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      workflow: {
        frame_confirmed: true,
        active_step: 'spec' as const,
        spec_confirmed: true,
        execution_started: true,
        execution_completed: true,
        shaping_frozen: true,
        can_finish_task: false,
        execution_status: 'completed' as const,
      },
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec' as const,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: true,
      execution_started: true,
      execution_completed: true,
      shaping_frozen: true,
      can_finish_task: false,
      execution_status: 'completed' as const,
      audit_writable: true,
      package_audit_ready: false,
      review_status: null,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          status: 'in_progress',
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: true,
            execution_status: 'completed',
          },
        })}
        variant="graph"
        showClose={false}
      />,
    )

    expect(screen.getByText('In Progress')).toBeInTheDocument()
    await screen.findByDisplayValue('# Frame')
    expect(screen.queryByText('Execution Complete')).not.toBeInTheDocument()
  })

  it('flushes the active document immediately on blur', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Updated',
      updated_at: '2026-03-21T00:00:02Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const editor = await screen.findByTestId('mock-codemirror')
    fireEvent.change(editor, { target: { value: '# Updated' } })
    fireEvent.blur(editor)

    await waitFor(() => {
      expect(apiMock.putNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame', '# Updated')
    })
  })

  it('keeps the draft visible when saving fails', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockRejectedValue(new Error('save failed'))

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const editor = await screen.findByTestId('mock-codemirror')
    fireEvent.change(editor, { target: { value: '# Draft' } })
    fireEvent.blur(editor)

    await waitFor(() => {
      expect(screen.getByText('save failed')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('# Draft')).toBeInTheDocument()
  })

  it('disables Confirm button when frame content is empty', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    })
    expect(screen.getByTestId('confirm-document-frame')).toBeDisabled()
  })

  it('calls confirmFrame and refreshes snapshot on workflow confirm', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame content',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame content',
      updated_at: '2026-03-21T00:00:01Z',
    })
    apiMock.confirmFrame.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'clarify',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: false,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getSnapshot.mockResolvedValue({
      schema_version: 1,
      project: { id: 'project-1', name: 'Test' },
      tree_state: { root_node_id: 'root', active_node_id: 'root', node_registry: [] },
      updated_at: '2026-03-21T00:00:02Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Frame content')
    const confirmBtn = screen.getByTestId('confirm-document-frame')
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)
    expect(confirmBtn).toHaveTextContent('Confirming...')

    await waitFor(() => {
      expect(apiMock.confirmFrame).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(apiMock.getSnapshot).toHaveBeenCalledWith('project-1')
    })
    expect(confirmBtn).toHaveTextContent('Confirm')
  })

  it('shows error when confirm fails', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame content',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame content',
      updated_at: '2026-03-21T00:00:01Z',
    })
    apiMock.confirmFrame.mockRejectedValue(new Error('Frame is empty'))

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Frame content')
    fireEvent.click(screen.getByTestId('confirm-document-frame'))

    await waitFor(() => {
      expect(screen.getByTestId('confirm-error-frame')).toHaveTextContent('Frame is empty')
    })
  })

  it('all tabs are always clickable (no locked state)', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    })

    // All tabs should be clickable
    expect(screen.getByRole('button', { name: 'Describe' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Frame' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Clarify' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Spec' })).not.toBeDisabled()
  })

  it('shows error banner with retry when detail state fails to load', async () => {
    apiMock.getDetailState.mockRejectedValue(new Error('Network error'))
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument()
    })

    // Retry button should re-fetch
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      active_step: 'frame' as const,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(screen.queryByText(/Network error/)).not.toBeInTheDocument()
    })
  })

  it('does not show a generation error banner when spec is no longer auto-started', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      active_step: 'spec',
      workflow_notice: null,
      generation_error: 'Spec generation is already in progress for this node.',
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Spec')
    expect(screen.queryByTestId('generation-error-banner')).not.toBeInTheDocument()
    expect(screen.getByTestId('confirm-and-finish-task-button')).toBeInTheDocument()
  })

  it('loads the next node document when the selected node changes', async () => {
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Root Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'child-1',
        kind: 'frame',
        content: '# Child Frame',
        updated_at: '2026-03-21T00:00:01Z',
      })

    const view = render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Root Frame')

    view.rerender(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ node_id: 'child-1', title: 'Child', description: 'Child node' })}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'child-1', 'frame')
    })
    expect(screen.getByDisplayValue('# Child Frame')).toBeInTheDocument()
  })

  it('calls confirmSpec on spec tab workflow confirm', async () => {
    // Set active_step to spec so buttons are visible and spec is not read-only
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'spec',
      content: '# Spec content',
      updated_at: '2026-03-21T00:00:02Z',
    })
    apiMock.confirmSpec.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: true,
    })
    apiMock.finishTask.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: true,
      execution_status: 'executing',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    // Switch to Spec tab
    const specButton = await screen.findByRole('button', { name: 'Spec' })
    fireEvent.click(specButton)

    await screen.findByDisplayValue('# Spec content')
    const confirmBtn = screen.getByTestId('confirm-and-finish-task-button')
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(apiMock.finishTask).toHaveBeenCalledWith('project-1', 'root')
    })
  })

  it('routes Confirm and Finish Task through workflow v2 when the execution/audit surface flag is enabled', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
        execution_audit_v2_enabled: true,
      },
    })
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
      can_finish_task: true,
      shaping_frozen: false,
      git_ready: true,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'spec',
      content: '# Spec content',
      updated_at: '2026-03-21T00:00:02Z',
    })
    apiMock.confirmSpec.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: true,
    })
    apiMock.getSnapshot.mockResolvedValue({
      schema_version: 1,
      project: { id: 'project-1', name: 'Test' },
      tree_state: { root_node_id: 'root', active_node_id: 'root', node_registry: [] },
      updated_at: '2026-03-21T00:00:03Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Spec' }))
    await screen.findByDisplayValue('# Spec content')

    fireEvent.click(screen.getByTestId('confirm-and-finish-task-button'))

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(apiMock.finishTaskWorkflowV2).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.stringMatching(/^finish_task:/),
      )
    })
    await waitFor(() => {
      expect(apiMock.getWorkflowStateV2).toHaveBeenCalledWith('project-1', 'root')
    })
    expect(apiMock.finishTask).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/projects/project-1/nodes/root/chat-v2?thread=execution')
  })

  it('disables Confirm and Finish Task when finish would still be blocked after confirm', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
      can_finish_task: false,
      git_ready: false,
      git_blocker_message: 'Workspace has uncommitted changes.',
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    const specButton = await screen.findByRole('button', { name: 'Spec' })
    fireEvent.click(specButton)

    await screen.findByDisplayValue('# Spec content')
    expect(screen.getByTestId('confirm-and-finish-task-button')).toBeDisabled()
  })

  it('confirms the updated frame, opens Split tab, and submits the chosen split mode', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      activeProjectId: 'project-1',
    })
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 3,
      active_step: 'frame',
      workflow_notice: 'Clarify decisions were applied to the frame. Review and confirm the updated frame.',
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: true,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Updated frame content',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Updated frame content',
      updated_at: '2026-03-21T00:00:01Z',
    })
    apiMock.confirmFrame.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 3,
      frame_revision: 3,
      active_step: 'spec',
      workflow_notice: null,
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getSnapshot.mockResolvedValue({
      schema_version: 1,
      project: { id: 'project-1', name: 'Test' },
      tree_state: { root_node_id: 'root', active_node_id: 'root', node_registry: [] },
      updated_at: '2026-03-21T00:00:02Z',
    })
    apiMock.splitNode.mockResolvedValue({
      status: 'accepted',
      job_id: 'split-job-1',
      node_id: 'root',
      mode: 'phase_breakdown',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Updated frame content')
    fireEvent.click(screen.getByTestId('confirm-and-split-button'))

    await waitFor(() => {
      expect(apiMock.confirmFrame).toHaveBeenCalledWith('project-1', 'root')
    })

    expect(await screen.findByRole('heading', { level: 3, name: /Choose how this task should be broken down/i })).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('split-option-phase_breakdown'))
    fireEvent.click(screen.getByTestId('confirm-split-button'))

    await waitFor(() => {
      expect(apiMock.splitNode).toHaveBeenCalledWith('project-1', 'root', 'phase_breakdown')
    })
  })

  it('shows both updated-frame actions when the frame-updated branch is ready', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 3,
      active_step: 'frame',
      workflow_notice: 'Clarify decisions were applied to the frame. Review and confirm the updated frame.',
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: true,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Updated frame content',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Updated frame content')
    expect(screen.getByTestId('confirm-and-split-button')).toBeInTheDocument()
    expect(screen.getByTestId('confirm-and-create-spec-button')).toBeInTheDocument()
  })

  it('routes Frame Updated back to the active workflow step when no updated-frame branch is pending', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      active_step: 'spec' as const,
      workflow_notice: null,
      generation_error: null,
      frame_branch_ready: false,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame content',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Spec content')
    fireEvent.click(screen.getByRole('button', { name: 'Frame Updated' }))

    expect(screen.getByDisplayValue('# Spec content')).toBeInTheDocument()
    expect(screen.queryByTestId('confirm-and-split-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('confirm-and-create-spec-button')).not.toBeInTheDocument()
  })

  it('keeps Split available during the normal spec workflow', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      active_step: 'spec' as const,
      workflow_notice: null,
      generation_error: null,
      frame_branch_ready: false,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: false,
      spec_confirmed: false,
      can_finish_task: false,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame content',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Spec content')
    const splitButton = screen.getByRole('button', { name: 'Split' })
    expect(splitButton).not.toBeDisabled()

    fireEvent.click(splitButton)

    expect(
      await screen.findByRole('heading', {
        level: 3,
        name: /Choose how this task should be broken down/i,
      }),
    ).toBeInTheDocument()
  })

  it('switches to Spec after Confirm and Create Spec from Frame Updated', async () => {
    apiMock.getDetailState
      .mockResolvedValueOnce({
        node_id: 'root',
        frame_confirmed: true,
        frame_confirmed_revision: 2,
        frame_revision: 3,
        active_step: 'frame' as const,
        workflow_notice: 'Clarify decisions were applied to the frame. Review and confirm the updated frame.',
        generation_error: null,
        frame_branch_ready: true,
        frame_needs_reconfirm: true,
        frame_read_only: false,
        clarify_read_only: true,
        clarify_confirmed: true,
        spec_read_only: true,
        spec_stale: false,
        spec_confirmed: false,
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        frame_confirmed: true,
        frame_confirmed_revision: 3,
        frame_revision: 3,
        active_step: 'spec' as const,
        workflow_notice: null,
        generation_error: null,
        frame_branch_ready: false,
        frame_needs_reconfirm: false,
        frame_read_only: true,
        clarify_read_only: true,
        clarify_confirmed: true,
        spec_read_only: false,
        spec_stale: false,
        spec_confirmed: false,
      })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Updated frame content',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Generated spec content',
        updated_at: '2026-03-21T00:00:01Z',
      })
    apiMock.confirmFrame.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 3,
      frame_revision: 3,
      active_step: 'spec',
      workflow_notice: null,
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.generateSpec.mockResolvedValue({
      status: 'accepted',
      job_id: 'sgen_1',
      node_id: 'root',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Updated frame content')
    fireEvent.click(screen.getByTestId('confirm-and-create-spec-button'))

    await waitFor(() => {
      expect(apiMock.generateSpec).toHaveBeenCalledWith('project-1', 'root')
    })

    expect(await screen.findByDisplayValue('# Generated spec content')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Split' })).toBeDisabled()
  })

  it('clears a stale post-update branch when a new Frame Updated cycle starts', async () => {
    sessionStorage.setItem('planningtree:framePostUpdate:project-1:root', 'spec')
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 3,
      active_step: 'frame' as const,
      workflow_notice: 'Clarify decisions were applied to the frame. Review and confirm the updated frame.',
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: true,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Updated frame content',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="graph"
        showClose={false}
      />,
    )

    const splitButton = await screen.findByTestId('confirm-and-split-button')
    await waitFor(() => {
      expect(splitButton).not.toBeDisabled()
    })
  })

  it('shows Generate from Chat button on frame tab', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('generate-frame-button')).toBeInTheDocument()
    })
    expect(screen.getByTestId('generate-frame-button')).toHaveTextContent('Generate from Chat')
  })

  it('calls generateFrame and shows Generating state', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.generateFrame.mockResolvedValue({
      status: 'accepted',
      job_id: 'fgen_123',
      node_id: 'root',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: '2026-03-21T00:00:05Z',
      error: null,
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    await waitFor(() => {
      expect(within(genBtn).getByRole('status', { name: 'Generating' })).toBeInTheDocument()
    })
    expect(apiMock.generateFrame).toHaveBeenCalledWith('project-1', 'root')
  })

  it('shows error when generateFrame fails', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.generateFrame.mockRejectedValue(new Error('Codex unavailable'))

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    await waitFor(() => {
      expect(screen.getByTestId('generate-error-frame')).toHaveTextContent('Codex unavailable')
    })
  })

  it('recovers active generation state on mount', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Old frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'active',
      job_id: 'fgen_456',
      started_at: '2026-03-21T00:00:00Z',
      completed_at: null,
      error: null,
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    // Should show Generating state from recovery
    await waitFor(() => {
      expect(
        within(screen.getByTestId('generate-frame-button')).getByRole('status', {
          name: 'Generating',
        }),
      ).toBeInTheDocument()
    })
    // Confirm should be disabled while generating
    expect(screen.getByTestId('confirm-document-frame')).toBeDisabled()
  })

  it('disables editor and confirm while generating', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Some content',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'active',
      job_id: 'fgen_789',
      started_at: '2026-03-21T00:00:00Z',
      completed_at: null,
      error: null,
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(
        within(screen.getByTestId('generate-frame-button')).getByRole('status', {
          name: 'Generating',
        }),
      ).toBeInTheDocument()
    })

    // Confirm button should be disabled
    expect(screen.getByTestId('confirm-document-frame')).toBeDisabled()
    // Generate button should also be disabled
    expect(screen.getByTestId('generate-frame-button')).toBeDisabled()
  })

  it('aborts generation when flush fails instead of overwriting unsaved content', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.putNodeDocument.mockRejectedValue(new Error('Network error'))

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    // Wait for document to fully load before editing
    await screen.findByDisplayValue('# Frame')

    // Edit to make content dirty
    const editor = screen.getByTestId('mock-codemirror')
    fireEvent.change(editor, { target: { value: '# User draft' } })

    // Click Generate — flush should fail, generation should NOT start
    fireEvent.click(screen.getByTestId('generate-frame-button'))

    await waitFor(() => {
      expect(screen.getByTestId('generate-error-frame')).toHaveTextContent(
        /could not save pending changes/i,
      )
    })
    // generateFrame should never have been called
    expect(apiMock.generateFrame).not.toHaveBeenCalled()
    // Button should still say "Generate from Chat" (not "Generating...")
    expect(screen.getByTestId('generate-frame-button')).toHaveTextContent('Generate from Chat')
  })

  it('attaches to active job instead of showing error when generation is already running', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    // Mount recovery returns idle (simulating race where recovery didn't catch it)
    apiMock.getFrameGenStatus
      .mockResolvedValueOnce({
        status: 'idle',
        job_id: null,
        started_at: null,
        completed_at: null,
        error: null,
      })
      // Subsequent poll calls return active
      .mockResolvedValue({
        status: 'active',
        job_id: 'fgen_existing',
        started_at: '2026-03-21T00:00:00Z',
        completed_at: null,
        error: null,
      })
    // Backend rejects because a job is already running
    apiMock.generateFrame.mockRejectedValue(
      new MockApiError(409, { message: 'Frame generation is already in progress for this node.', code: 'frame_generation_not_allowed' }),
    )

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    // Should show "Generating..." (attached to existing job) instead of error
    await waitFor(() => {
      expect(
        within(screen.getByTestId('generate-frame-button')).getByRole('status', {
          name: 'Generating',
        }),
      ).toBeInTheDocument()
    })
    // No error banner should be shown
    expect(screen.queryByTestId('generate-error-frame')).not.toBeInTheDocument()
  })

  it('shows stale banner on spec tab when spec_stale is true', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      active_step: 'spec',
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: false,
      spec_stale: true,
      spec_confirmed: true,
    })
    apiMock.getNodeDocument
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'frame',
        content: '# Frame',
        updated_at: '2026-03-21T00:00:00Z',
      })
      .mockResolvedValueOnce({
        node_id: 'root',
        kind: 'spec',
        content: '# Stale Spec',
        updated_at: '2026-03-21T00:00:01Z',
      })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    const specButton = await screen.findByRole('button', { name: 'Spec' })
    fireEvent.click(specButton)

    await waitFor(() => {
      expect(screen.getByTestId('stale-banner-spec')).toBeInTheDocument()
    })
    expect(screen.getByTestId('stale-banner-spec')).toHaveTextContent(
      /Frame was updated/,
    )
  })

  it('renders the review detail surface and accepts a rollup draft', async () => {
    apiMock.getDetailState
      .mockResolvedValueOnce(
        makeReviewDetailState({
          node_id: 'review-1',
          review_status: 'ready',
        }),
      )
      .mockResolvedValueOnce(
        makeReviewDetailState({
          node_id: 'review-1',
          review_status: 'accepted',
        }),
      )
      .mockResolvedValueOnce({
        node_id: 'root',
        frame_confirmed: true,
        frame_confirmed_revision: 1,
        frame_revision: 1,
        active_step: 'spec' as const,
        workflow_notice: null,
        generation_error: null,
        frame_needs_reconfirm: false,
        frame_read_only: true,
        clarify_read_only: true,
        clarify_confirmed: true,
        spec_read_only: true,
        spec_stale: false,
        spec_confirmed: true,
        execution_started: true,
        execution_completed: true,
        shaping_frozen: true,
        can_finish_task: false,
        can_accept_local_review: false,
        execution_status: 'review_accepted' as const,
        audit_writable: true,
        package_audit_ready: true,
        review_status: 'accepted' as const,
      })
    apiMock.getReviewState
      .mockResolvedValueOnce({
        checkpoints: [
          {
            label: 'K0',
            sha: 'sha256:checkpoint',
            summary: 'Child review accepted.',
            source_node_id: 'child-1',
            accepted_at: '2026-03-24T00:00:00Z',
          },
        ],
        rollup: {
          status: 'ready',
          summary: null,
          sha: null,
          accepted_at: null,
          draft: {
            summary: 'Rollup draft summary',
            sha: 'sha256:draft',
            generated_at: '2026-03-24T00:05:00Z',
          },
        },
        pending_siblings: [
          {
            index: 2,
            title: 'Child 2',
            objective: 'Finish follow-up work',
            materialized_node_id: 'child-2',
          },
        ],
        sibling_manifest: [
          {
            index: 1,
            title: 'Child 1',
            objective: 'Ship base work',
            materialized_node_id: 'child-1',
            status: 'completed',
            checkpoint_label: 'K1',
          },
          {
            index: 2,
            title: 'Child 2',
            objective: 'Finish follow-up work',
            materialized_node_id: 'child-2',
            status: 'active',
            checkpoint_label: null,
          },
        ],
      })
      .mockResolvedValueOnce({
        checkpoints: [
          {
            label: 'K0',
            sha: 'sha256:checkpoint',
            summary: 'Child review accepted.',
            source_node_id: 'child-1',
            accepted_at: '2026-03-24T00:00:00Z',
          },
        ],
        rollup: {
          status: 'accepted',
          summary: 'Accepted rollup summary',
          sha: 'sha256:accepted',
          accepted_at: '2026-03-24T00:10:00Z',
          draft: {
            summary: null,
            sha: null,
            generated_at: null,
          },
        },
        pending_siblings: [
          {
            index: 2,
            title: 'Child 2',
            objective: 'Finish follow-up work',
            materialized_node_id: 'child-2',
          },
        ],
        sibling_manifest: [
          {
            index: 1,
            title: 'Child 1',
            objective: 'Ship base work',
            materialized_node_id: 'child-1',
            status: 'completed',
            checkpoint_label: 'K1',
          },
          {
            index: 2,
            title: 'Child 2',
            objective: 'Finish follow-up work',
            materialized_node_id: 'child-2',
            status: 'active',
            checkpoint_label: null,
          },
        ],
      })
    apiMock.getSnapshot.mockResolvedValue({
      schema_version: 6,
      project: {
        id: 'project-1',
        name: 'Project',
        root_goal: 'Goal',
        project_path: 'C:/workspace/project-1',
        created_at: '2026-03-24T00:00:00Z',
        updated_at: '2026-03-24T00:00:00Z',
      },
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'review-1',
        node_registry: [
          {
            ...makeNode({
              node_id: 'root',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec',
                spec_confirmed: true,
                execution_status: 'review_accepted',
              },
            }),
            review_node_id: 'review-1',
          },
          makeNode({
            node_id: 'review-1',
            parent_id: 'root',
            status: 'ready',
            node_kind: 'review',
            title: 'Review',
            hierarchical_number: '1.R',
            workflow: null,
          }),
        ],
      },
      updated_at: '2026-03-24T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          node_id: 'review-1',
          parent_id: 'root',
          status: 'ready',
          node_kind: 'review',
          title: 'Review',
          hierarchical_number: '1.R',
          workflow: null,
        })}
        variant="graph"
        showClose={false}
      />,
    )

    expect(await screen.findByTestId('review-detail-panel')).toBeInTheDocument()
    expect(screen.getByText('Child review accepted.')).toBeInTheDocument()
    expect(screen.getByText('Completed siblings')).toBeInTheDocument()
    expect(screen.getByText('1.A Child 1')).toBeInTheDocument()
    expect(screen.getByText('Current active sibling')).toBeInTheDocument()
    expect(screen.getByText('1.B Child 2')).toBeInTheDocument()
    expect(screen.getByText('Remaining pending siblings')).toBeInTheDocument()
    expect(screen.getByText('Rollup draft summary')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('accept-rollup-button'))

    await waitFor(() => {
      expect(apiMock.acceptRollupReview).toHaveBeenCalledWith('project-1', 'review-1')
    })
    expect(await screen.findByText('Accepted rollup summary')).toBeInTheDocument()
  })

  it('shows a package-audit-ready banner on parent task nodes', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'spec' as const,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: true,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: true,
      execution_started: true,
      execution_completed: true,
      shaping_frozen: true,
      can_finish_task: false,
      can_accept_local_review: false,
      execution_status: 'review_accepted' as const,
      audit_writable: true,
      package_audit_ready: true,
      review_status: 'accepted' as const,
    })
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          status: 'done',
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: true,
            execution_status: 'review_accepted',
          },
        })}
        variant="graph"
        showClose={false}
      />,
    )

    expect(await screen.findByTestId('package-audit-ready-banner')).toHaveTextContent(
      /Package audit ready/i,
    )
  })
})
