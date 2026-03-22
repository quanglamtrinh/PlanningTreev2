import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
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

    fireEvent.click(screen.getByRole('button', { name: 'Spec' }))

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
})
