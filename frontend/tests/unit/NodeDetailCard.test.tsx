import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
    getDetailState: vi.fn().mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      clarify_unlocked: true,
      clarify_stale: false,
      clarify_confirmed: false,
      spec_unlocked: true,
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
  },
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

vi.mock('../../src/api/client', () => {
  class ApiError extends Error {
    status: number
    code: string | null

    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  }

  return {
    api: apiMock,
    ApiError,
  }
})

import type { NodeRecord } from '../../src/api/types'
import { NodeDetailCard } from '../../src/features/node/NodeDetailCard'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useClarifyStore } from '../../src/stores/clarify-store'

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
    ...overrides,
  }
}

describe('NodeDetailCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    useNodeDocumentStore.getState().reset()
    useDetailStateStore.getState().reset()
    useClarifyStore.getState().reset()
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
        node={makeNode()}
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
      clarify_unlocked: true,
      clarify_stale: false,
      clarify_confirmed: false,
      spec_unlocked: false,
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

  it('locks Clarify and Spec tabs when detail state says they are locked', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      clarify_unlocked: false,
      clarify_stale: false,
      clarify_confirmed: false,
      spec_unlocked: false,
      spec_stale: false,
      spec_confirmed: false,
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
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    // Wait for detail state to load
    await waitFor(() => {
      expect(apiMock.getDetailState).toHaveBeenCalledWith('project-1', 'root')
    })

    // Clarify and Spec should be disabled with accessible locked label
    await waitFor(() => {
      const clarifyBtn = screen.getByRole('button', { name: 'Clarify (locked)' })
      expect(clarifyBtn).toBeDisabled()
    })
    const specBtn = screen.getByRole('button', { name: 'Spec (locked)' })
    expect(specBtn).toBeDisabled()
    await waitFor(() => {
      expect(screen.getByText('Confirm Frame to unlock Clarify.')).toBeInTheDocument()
    })

    // Describe and Frame should remain clickable
    expect(screen.getByRole('button', { name: 'Describe' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: 'Frame' })).not.toBeDisabled()
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
      clarify_unlocked: true,
      clarify_stale: false,
      clarify_confirmed: false,
      spec_unlocked: true,
      spec_stale: false,
      spec_confirmed: false,
    })
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(screen.queryByText(/Network error/)).not.toBeInTheDocument()
    })
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
      clarify_unlocked: true,
      clarify_stale: false,
      clarify_confirmed: true,
      spec_unlocked: true,
      spec_stale: false,
      spec_confirmed: true,
    })

    render(
      <NodeDetailCard
        projectId="project-1"
        node={makeNode()}
        variant="graph"
        showClose={false}
      />,
    )

    // Switch to Spec tab
    const specButton = await screen.findByRole('button', { name: 'Spec' })
    fireEvent.click(specButton)

    await screen.findByDisplayValue('# Spec content')
    const confirmBtn = screen.getByTestId('confirm-document-spec')
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(apiMock.confirmSpec).toHaveBeenCalledWith('project-1', 'root')
    })
  })

  it('shows stale banner on spec tab when spec_stale is true', async () => {
    apiMock.getDetailState.mockResolvedValue({
      node_id: 'root',
      frame_confirmed: true,
      frame_confirmed_revision: 2,
      frame_revision: 2,
      clarify_unlocked: true,
      clarify_stale: false,
      clarify_confirmed: true,
      spec_unlocked: true,
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
      /Frame or Clarify was updated/,
    )
  })
})
