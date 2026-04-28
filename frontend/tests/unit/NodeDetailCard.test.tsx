import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, workflowV2ApiMock, MockApiError, navigateMock } = vi.hoisted(() => ({
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
    listMcpRegistry: vi.fn(),
    readMcpThreadProfile: vi.fn(),
    previewMcpEffectiveConfig: vi.fn(),
    updateMcpThreadProfile: vi.fn(),
  },
  workflowV2ApiMock: {
    getWorkflowStateV2: vi.fn(),
    ensureWorkflowThreadV2: vi.fn(),
    startExecutionV2: vi.fn(),
    markDoneFromExecutionV2: vi.fn(),
    startAuditV2: vi.fn(),
    improveExecutionV2: vi.fn(),
    acceptAuditV2: vi.fn(),
    startPackageReviewV2: vi.fn(),
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
  appendAuthToken: (url: string) => url,
  initAuthToken: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../src/features/workflow_v2/api/client', () => ({
  getWorkflowStateV2: workflowV2ApiMock.getWorkflowStateV2,
  ensureWorkflowThreadV2: workflowV2ApiMock.ensureWorkflowThreadV2,
  startExecutionV2: workflowV2ApiMock.startExecutionV2,
  markDoneFromExecutionV2: workflowV2ApiMock.markDoneFromExecutionV2,
  startAuditV2: workflowV2ApiMock.startAuditV2,
  improveExecutionV2: workflowV2ApiMock.improveExecutionV2,
  acceptAuditV2: workflowV2ApiMock.acceptAuditV2,
  startPackageReviewV2: workflowV2ApiMock.startPackageReviewV2,
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
import { askShellNodeActionStateKey, useAskShellActionStore } from '../../src/stores/ask-shell-action-store'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useClarifyStore } from '../../src/stores/clarify-store'
import { useProjectStore } from '../../src/stores/project-store'
import { useWorkflowStateStoreV2 } from '../../src/features/workflow_v2/store/workflowStateStoreV2'

function makeNode(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    node_id: 'root',
    parent_id: null,
    child_ids: [],
    title: 'Root',
    description: 'Root node',
    status: 'draft',
    node_kind: 'original',
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

function makeWorkflowStateV2(overrides: Record<string, unknown> = {}) {
  return {
    schemaVersion: 1,
    projectId: 'project-1',
    nodeId: 'root',
    phase: 'executing',
    version: 1,
    threads: {
      askPlanning: 'thread-ask-1',
      execution: 'thread-execution-1',
      audit: 'thread-audit-lineage-1',
      packageReview: null,
    },
    decisions: {
      execution: null,
      audit: null,
    },
    context: {
      frameVersion: 1,
      specVersion: 1,
      splitManifestVersion: null,
    },
    allowedActions: [],
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
    useAskShellActionStore.getState().reset()
    useWorkflowStateStoreV2.getState().reset()
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
    apiMock.listMcpRegistry.mockResolvedValue({ servers: [] })
    apiMock.readMcpThreadProfile.mockImplementation((projectId: string, nodeId: string, role: string) =>
      Promise.resolve({
        profile: {
          projectId,
          nodeId,
          role,
          threadId: null,
          mcpEnabled: false,
          approvalMode: 'never',
          servers: {},
          updatedAt: '2026-03-21T00:00:00Z',
        },
      }),
    )
    apiMock.previewMcpEffectiveConfig.mockImplementation((projectId: string, nodeId: string, role: string) =>
      Promise.resolve({
        projectId,
        nodeId,
        role,
        threadId: null,
        profile: {
          projectId,
          nodeId,
          role,
          threadId: null,
          mcpEnabled: false,
          approvalMode: 'never',
          servers: {},
          updatedAt: '2026-03-21T00:00:00Z',
        },
        effectiveConfig: {},
        mcpConfigHash: 'sha256:empty',
        runtime: {
          activeRuntimeMcpConfigHash: null,
          conflict: false,
          status: null,
          lastStartedAt: null,
          lastStoppedAt: null,
        },
      }),
    )
    apiMock.updateMcpThreadProfile.mockResolvedValue({
      profile: {
        projectId: 'project-1',
        nodeId: 'root',
        role: 'root',
        threadId: null,
        mcpEnabled: true,
        approvalMode: 'never',
        servers: {},
        updatedAt: '2026-03-21T00:00:00Z',
      },
    })
    workflowV2ApiMock.startExecutionV2.mockResolvedValue({
      accepted: true,
      threadId: 'thread-execution-1',
      turnId: 'turn-1',
      executionRunId: 'run-1',
      workflowState: makeWorkflowStateV2(),
    })
    workflowV2ApiMock.getWorkflowStateV2.mockResolvedValue(makeWorkflowStateV2())
  })

  it('graph variant shows only info (describe) without workflow stepper or editors', async () => {
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

    expect(screen.queryByTestId('workflow-stepper')).not.toBeInTheDocument()
    expect(screen.queryByRole('tablist', { name: 'Task document sections' })).not.toBeInTheDocument()
    expect(screen.getByText('Root node')).toBeInTheDocument()
    expect(screen.queryByTestId('confirm-document-frame')).not.toBeInTheDocument()
    expect(apiMock.getNodeDocument).not.toHaveBeenCalled()
  })

  it('breadcrumb root node renders Info only and loads only the root MCP profile', async () => {
    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ node_kind: 'root', is_init_node: true })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(apiMock.readMcpThreadProfile).toHaveBeenCalledWith('project-1', 'root', 'root')
    })

    expect(screen.queryByTestId('workflow-stepper')).not.toBeInTheDocument()
    expect(screen.queryByRole('tablist', { name: 'Task document sections' })).not.toBeInTheDocument()
    expect(screen.getByText('Root node')).toBeInTheDocument()
    expect(screen.getByTestId('info-tab-mcp-role-root')).toBeInTheDocument()
    expect(screen.queryByTestId('info-tab-mcp-role-ask_planning')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Frame' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Clarify' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Spec' })).not.toBeInTheDocument()
    expect(apiMock.getNodeDocument).not.toHaveBeenCalled()
    expect(apiMock.readMcpThreadProfile.mock.calls.map((call) => call[2])).toEqual(['root'])
  })

  it('normalizes nodeMetaRow index by stripping init prefix for task nodes', () => {
    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          node_id: 'task-1',
          parent_id: 'init-1',
          node_kind: 'original',
          title: 'Task 1',
          hierarchical_number: '1.1',
        })}
        variant="graph"
        showClose={false}
      />,
    )

    const card = screen.getByTestId('graph-node-detail-card')
    expect(within(card).getByText('1')).toBeInTheDocument()
    expect(within(card).queryByText('1.1')).not.toBeInTheDocument()
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    })
    expect(screen.getByDisplayValue('# Frame')).toBeInTheDocument()
  })

  it('shows Edit and Rich View toggle controls in both Frame and Spec tabs', async () => {
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Frame')
    expect(screen.getByTestId('document-view-edit-frame')).toBeInTheDocument()
    expect(screen.getByTestId('document-view-rich-frame')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Spec' }))
    await screen.findByDisplayValue('# Spec')
    expect(screen.getByTestId('document-view-edit-spec')).toBeInTheDocument()
    expect(screen.getByTestId('document-view-rich-spec')).toBeInTheDocument()
  })

  it('renders Rich View from the current unsaved draft content', async () => {
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const editor = await screen.findByTestId('mock-codemirror')
    fireEvent.change(editor, { target: { value: 'Draft preview paragraph' } })
    fireEvent.click(screen.getByTestId('document-view-rich-frame'))

    expect(screen.getByTestId('document-rich-view-frame')).toBeInTheDocument()
    expect(screen.getByText('Draft preview paragraph')).toBeInTheDocument()
    expect(apiMock.putNodeDocument).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('document-view-edit-frame'))
    expect(screen.getByDisplayValue('Draft preview paragraph')).toBeInTheDocument()
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    // Wait for detail state to load so Spec tab is unlocked
    const specButton = await screen.findByRole('tab', { name: 'Spec' })
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
        variant="breadcrumb"
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
        variant="breadcrumb"
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
        variant="breadcrumb"
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
        variant="breadcrumb"
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
        variant="breadcrumb"
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
      expect(apiMock.generateClarify).toHaveBeenCalledWith('project-1', 'root')
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
        variant="breadcrumb"
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    })

    // Stepper tabs (Describe removed from exploration region; Info stays on breadcrumb tabs)
    expect(screen.getByRole('tab', { name: 'Frame' })).not.toBeDisabled()
    expect(screen.getByRole('tab', { name: 'Clarify' })).not.toBeDisabled()
    expect(screen.getByRole('tab', { name: 'Spec' })).not.toBeDisabled()
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
        variant="breadcrumb"
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

  it('keeps breadcrumb detail rendering without an error banner when stale detail state exists', async () => {
    apiMock.getDetailState.mockRejectedValue(new Error('Request timed out after 300s'))
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })

    useDetailStateStore.setState({
      entries: {
        'project-1::root': {
          node_id: 'root',
          frame_confirmed: true,
          frame_confirmed_revision: 1,
          frame_revision: 1,
          active_step: 'spec',
          workflow_notice: null,
          generation_error: null,
          frame_needs_reconfirm: false,
          frame_read_only: true,
          clarify_read_only: true,
          clarify_confirmed: true,
          spec_read_only: false,
          spec_stale: false,
          spec_confirmed: true,
        },
      },
    } as Partial<ReturnType<typeof useDetailStateStore.getState>>)

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(useDetailStateStore.getState().errors['project-1::root']).toBe(
        'Request timed out after 300s',
      )
    })

    expect(screen.queryByText(/Failed to load detail state/i)).not.toBeInTheDocument()
    expect(screen.getByText('Root')).toBeInTheDocument()
  })

  it('breadcrumb shows indicative workflow stepper and document tabs for navigation', async () => {
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    })

    const stepper = screen.getByTestId('workflow-stepper')
    expect(stepper).toHaveAttribute('data-stepper-mode', 'indicative')
    expect(stepper).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('navigation', { name: 'Task workflow steps' })).not.toBeInTheDocument()
    expect(screen.getByRole('tablist', { name: 'Task document sections' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Info' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Frame' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Split' })).not.toBeInTheDocument()
  })

  it('breadcrumb shows Split tab when frame_branch_ready', async () => {
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-21T00:00:00Z',
    })
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 1,
      frame_revision: 1,
      active_step: 'frame' as const,
      frame_branch_ready: true,
      workflow_notice: null,
      generation_error: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: true,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    expect(await screen.findByRole('tab', { name: 'Split' })).toBeInTheDocument()
  })

  it('breadcrumb loads spec.md when the Spec tab is clicked', async () => {
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const specTab = await screen.findByRole('tab', { name: 'Spec' })
    fireEvent.click(specTab)

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'root', 'spec')
    })
    expect(screen.getByDisplayValue('# Spec')).toBeInTheDocument()
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
        variant="breadcrumb"
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Root Frame')

    view.rerender(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ node_id: 'child-1', title: 'Child', description: 'Child node' })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getNodeDocument).toHaveBeenCalledWith('project-1', 'child-1', 'frame')
    })
    expect(screen.getByDisplayValue('# Child Frame')).toBeInTheDocument()
  })

  it('calls confirmSpec and workflow finish on spec tab confirm', async () => {
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
    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({ status: 'ready' })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    // Switch to Spec tab
    const specButton = await screen.findByRole('tab', { name: 'Spec' })
    fireEvent.click(specButton)

    await screen.findByDisplayValue('# Spec content')
    const confirmBtn = screen.getByTestId('confirm-and-finish-task-button')
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(workflowV2ApiMock.startExecutionV2).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          idempotencyKey: expect.stringMatching(/^start_execution:/),
          model: null,
          modelProvider: null,
        }),
      )
    })
  })

  it('routes Confirm and Finish Task through workflow v2 flow', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    fireEvent.click(await screen.findByRole('tab', { name: 'Spec' }))
    await screen.findByDisplayValue('# Spec content')

    fireEvent.click(screen.getByTestId('confirm-and-finish-task-button'))

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
    })
    await waitFor(() => {
      expect(workflowV2ApiMock.startExecutionV2).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          idempotencyKey: expect.stringMatching(/^start_execution:/),
          model: null,
          modelProvider: null,
        }),
      )
    })
    expect(apiMock.finishTask).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/projects/project-1/nodes/root/chat-v2?thread=execution')
  })

  it('disables Confirm and Finish Task immediately after click while request is pending', async () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
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

    const confirmSpecResponse = {
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
    }
    let resolveConfirmSpec: (() => void) | null = null
    apiMock.confirmSpec.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveConfirmSpec = () => resolve(confirmSpecResponse)
        }),
    )
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    fireEvent.click(await screen.findByRole('tab', { name: 'Spec' }))
    await screen.findByDisplayValue('# Spec content')

    const finishButton = screen.getByTestId('confirm-and-finish-task-button')
    fireEvent.click(finishButton)

    expect(finishButton).toBeDisabled()
    expect(finishButton).toHaveTextContent('Finishing...')

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
      expect(resolveConfirmSpec).not.toBeNull()
    })

    if (!resolveConfirmSpec) {
      throw new Error('confirmSpec request was not started')
    }
    resolveConfirmSpec()

    await waitFor(() => {
      expect(workflowV2ApiMock.startExecutionV2).toHaveBeenCalledWith(
        'project-1',
        'root',
        expect.objectContaining({
          idempotencyKey: expect.stringMatching(/^start_execution:/),
          model: null,
          modelProvider: null,
        }),
      )
    })
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/projects/project-1/nodes/root/chat-v2?thread=execution')
    })
    await waitFor(() => {
      expect(finishButton).toBeDisabled()
    })
    expect(finishButton).toHaveTextContent('Confirm and Finish Task')
    expect(screen.queryByTestId('finish-task-disabled-hint')).not.toBeInTheDocument()
    expect(finishButton).toHaveAttribute('title', 'Finish Task was already confirmed for this run.')
  })

  it('does not refetch spec generation status on a stable rerender', async () => {
    useDetailStateStore.setState({
      entries: {
        'project-1::root': {
          node_id: 'root',
          frame_confirmed: true,
          frame_confirmed_revision: 1,
          frame_revision: 1,
          active_step: 'spec',
          workflow_notice: null,
          generation_error: null,
          frame_needs_reconfirm: false,
          frame_read_only: true,
          clarify_read_only: true,
          clarify_confirmed: true,
          spec_read_only: false,
          spec_stale: false,
          spec_confirmed: false,
        },
      },
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

    const view = render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: false,
          },
        })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getSpecGenStatus).toHaveBeenCalledTimes(1)
    })

    view.rerender(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode({
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: false,
          },
        })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(apiMock.getSpecGenStatus).toHaveBeenCalledTimes(1)
    })
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    expect(screen.queryByText('Workspace has uncommitted changes.')).not.toBeInTheDocument()

    const specButton = await screen.findByRole('tab', { name: 'Spec' })
    fireEvent.click(specButton)

    await screen.findByDisplayValue('# Spec content')
    expect(screen.getByText('Workspace has uncommitted changes.')).toBeInTheDocument()
    expect(screen.getByTestId('confirm-and-finish-task-button')).toBeDisabled()
    expect(screen.queryByTestId('finish-task-disabled-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('confirm-and-finish-task-button')).toHaveAttribute(
      'title',
      'Finish Task is disabled. Resolve Git blocker to continue.',
    )
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
        variant="breadcrumb"
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

  it('disables frame and split actions when the parent node has already been split', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 3,
      frame_revision: 3,
      active_step: 'frame',
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
      split_confirmed: true,
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
        node={makeNode({
          review_node_id: 'review-1',
          workflow: {
            frame_confirmed: true,
            active_step: 'spec',
            spec_confirmed: false,
            split_confirmed: true,
          },
        })}
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Updated frame content')

    expect(screen.getByTestId('confirm-and-split-button')).toBeDisabled()
    expect(screen.getByTestId('confirm-and-create-spec-button')).toBeDisabled()
    expect(screen.getByRole('tab', { name: 'Spec' })).toBeDisabled()

    fireEvent.click(screen.getByRole('tab', { name: 'Split' }))
    expect(await screen.findByTestId('split-readiness-hint')).toHaveTextContent(
      'This node has already been split.',
    )
    expect(screen.getByTestId('confirm-split-button')).toBeDisabled()
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
        variant="breadcrumb"
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Spec content')
    fireEvent.click(screen.getByRole('button', { name: 'Frame Updated', hidden: true }))

    expect(screen.getByDisplayValue('# Spec content')).toBeInTheDocument()
    expect(screen.queryByTestId('confirm-and-split-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('confirm-and-create-spec-button')).not.toBeInTheDocument()
  })

  it('keeps Split available during the normal spec workflow', async () => {
    /* frame_branch_ready shows Split tab; active_step must not be spec or initial tab becomes frame_updated-only */
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      active_step: 'frame' as const,
      workflow_notice: null,
      generation_error: null,
      frame_branch_ready: true,
      frame_needs_reconfirm: false,
      frame_read_only: false,
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Frame content')
    fireEvent.click(screen.getByRole('tab', { name: 'Spec' }))
    await screen.findByDisplayValue('# Spec content')

    const splitTab = screen.getByRole('tab', { name: 'Split' })
    expect(splitTab).not.toBeDisabled()
    fireEvent.click(splitTab)

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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await screen.findByDisplayValue('# Updated frame content')
    fireEvent.click(screen.getByTestId('confirm-and-create-spec-button'))

    await waitFor(() => {
      expect(apiMock.generateSpec).toHaveBeenCalledWith('project-1', 'root')
    })
    expect(apiMock.generateClarify).not.toHaveBeenCalled()

    expect(await screen.findByDisplayValue('# Generated spec content')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Split', hidden: true })).toBeDisabled()
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
        variant="breadcrumb"
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('generate-frame-button')).toBeInTheDocument()
    })
    expect(screen.getByTestId('generate-frame-button')).toHaveTextContent('Generate Frame')
  })

  it('calls generateFrame and shows body loading state', async () => {
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    await waitFor(() => {
      expect(screen.getByTestId('document-generating-frame')).toBeInTheDocument()
    })
    expect(apiMock.generateFrame).toHaveBeenCalledWith('project-1', 'root')
    const actionState = useAskShellActionStore.getState().entries[
      askShellNodeActionStateKey('project-1', 'root')
    ]
    expect(actionState?.frame.generate.status).toBe('running')
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    await waitFor(() => {
      expect(screen.getByTestId('generate-error-frame')).toHaveTextContent('Codex unavailable')
    })
    const actionState = useAskShellActionStore.getState().entries[
      askShellNodeActionStateKey('project-1', 'root')
    ]
    expect(actionState?.frame.generate.status).toBe('failed')
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    // Should show generating state from recovery in the document body
    await waitFor(() => {
      expect(screen.getByTestId('document-generating-frame')).toBeInTheDocument()
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('document-generating-frame')).toBeInTheDocument()
    })

    // Confirm button should be disabled
    expect(screen.getByTestId('confirm-document-frame')).toBeDisabled()
    // Generate button should also be disabled
    expect(screen.getByTestId('generate-frame-button')).toBeDisabled()
    // Editor is replaced by the body spinner while generation is active
    expect(screen.queryByTestId('mock-codemirror')).not.toBeInTheDocument()
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
        variant="breadcrumb"
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
    expect(screen.getByTestId('generate-frame-button')).toHaveTextContent('Generate Frame')
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const genBtn = await screen.findByTestId('generate-frame-button')
    fireEvent.click(genBtn)

    // Should attach to the active job and show body spinner instead of an error
    await waitFor(() => {
      expect(screen.getByTestId('document-generating-frame')).toBeInTheDocument()
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    const specButton = await screen.findByRole('tab', { name: 'Spec' })
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
        variant="breadcrumb"
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
        variant="breadcrumb"
        showClose={false}
      />,
    )

    expect(await screen.findByTestId('package-audit-ready-banner')).toHaveTextContent(
      /Package audit ready/i,
    )
  })
})

