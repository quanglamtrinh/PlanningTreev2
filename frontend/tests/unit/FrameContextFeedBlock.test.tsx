import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { NodeRecord } from '../../src/api/types'
import { FrameContextFeedBlock } from '../../src/features/breadcrumb/FrameContextFeedBlock'
import {
  askShellNodeActionStateKey,
  useAskShellActionStore,
} from '../../src/stores/ask-shell-action-store'
import { useClarifyStore } from '../../src/stores/clarify-store'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useProjectStore } from '../../src/stores/project-store'

function makeNode(overrides: Partial<NodeRecord> = {}): NodeRecord {
  return {
    node_id: 'root',
    parent_id: null,
    child_ids: [],
    title: 'Root task',
    description: 'Root description',
    status: 'draft',
    node_kind: 'root',
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    created_at: '2026-04-03T00:00:00Z',
    is_superseded: false,
    workflow: {
      frame_confirmed: true,
      active_step: 'clarify',
      spec_confirmed: false,
      shaping_frozen: false,
    },
    ...overrides,
  }
}

function makeTaskContext(taskOverrides: Partial<NodeRecord> = {}) {
  const taskId = taskOverrides.node_id ?? 'task-1'
  const initNode = makeNode({
    node_id: 'init',
    title: 'Workspace Init',
    node_kind: 'root',
    is_init_node: true,
    parent_id: null,
    child_ids: [taskId],
    hierarchical_number: '1',
  })
  const taskNode = makeNode({
    node_id: taskId,
    title: 'Root task',
    node_kind: 'original',
    is_init_node: false,
    parent_id: 'init',
    child_ids: [],
    hierarchical_number: '1.1',
    depth: 1,
    ...taskOverrides,
  })
  return { initNode, taskNode }
}

function seedDocumentStore(
  nodeId = 'root',
  {
    frameContent = '# Frame\nLogin flow',
    specContent = '# Spec\nAuth details',
  }: {
    frameContent?: string
    specContent?: string
  } = {},
) {
  const loadDocument = vi.fn().mockResolvedValue(undefined)
  useNodeDocumentStore.setState({
    ...useNodeDocumentStore.getState(),
    loadDocument,
    entries: {
      [`project-1::${nodeId}::frame`]: {
        content: frameContent,
        savedContent: frameContent,
        updatedAt: '2026-04-03T00:00:00Z',
        isLoading: false,
        isSaving: false,
        error: null,
        hasLoaded: true,
      },
      [`project-1::${nodeId}::spec`]: {
        content: specContent,
        savedContent: specContent,
        updatedAt: '2026-04-03T00:00:00Z',
        isLoading: false,
        isSaving: false,
        error: null,
        hasLoaded: true,
      },
    },
  } as Partial<ReturnType<typeof useNodeDocumentStore.getState>>)
  return loadDocument
}

function seedClarifyStore(nodeId = 'root') {
  const loadClarify = vi.fn().mockResolvedValue(undefined)
  useClarifyStore.setState({
    ...useClarifyStore.getState(),
    loadClarify,
    entries: {
      [`project-1::${nodeId}`]: {
        clarify: {
          schema_version: 2,
          source_frame_revision: 1,
          confirmed_revision: 0,
          confirmed_at: null,
          questions: [
            {
              field_name: 'auth_provider',
              question: 'What auth provider?',
              why_it_matters: '',
              current_value: '',
              options: [],
              selected_option_id: null,
              custom_answer: '',
              allow_custom: true,
            },
          ],
          updated_at: '2026-04-03T00:00:00Z',
        },
        savedQuestions: [],
        isLoading: false,
        isSaving: false,
        loadError: '',
        saveError: '',
        hasLoaded: true,
      },
    },
  } as Partial<ReturnType<typeof useClarifyStore.getState>>)
  return loadClarify
}

describe('FrameContextFeedBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useNodeDocumentStore.getState().reset()
    useClarifyStore.getState().reset()
    useAskShellActionStore.getState().reset()
    useProjectStore.setState(useProjectStore.getInitialState())
  })

  it('shows frame and clarify context even when shaping is not frozen', async () => {
    const { initNode, taskNode } = makeTaskContext()
    const loadDocument = seedDocumentStore(taskNode.node_id)
    const loadClarify = seedClarifyStore(taskNode.node_id)

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId={taskNode.node_id}
        nodeRegistry={[initNode, taskNode]}
        variant="ask"
      />,
    )

    expect(screen.queryByText(/Frame context will appear once clarify is confirmed/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Frame' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clarify' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clarify' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /^1\.\s*What auth provider\?$/i })).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(loadDocument).toHaveBeenCalledWith('project-1', taskNode.node_id, 'frame')
    })
    await waitFor(() => {
      expect(loadClarify).toHaveBeenCalledWith('project-1', taskNode.node_id)
    })
  })

  it('renders action status chips from shared action state', () => {
    const { initNode, taskNode } = makeTaskContext()
    seedDocumentStore(taskNode.node_id)
    seedClarifyStore(taskNode.node_id)

    const key = askShellNodeActionStateKey('project-1', taskNode.node_id)
    useAskShellActionStore.setState({
      entries: {
        [key]: {
          frame: {
            generate: { status: 'running', updatedAt: '2026-04-03T00:00:00Z', message: null },
            confirm: { status: 'idle', updatedAt: null, message: null },
          },
          clarify: {
            generate: { status: 'idle', updatedAt: null, message: null },
            confirm: { status: 'failed', updatedAt: '2026-04-03T00:00:00Z', message: 'failed' },
          },
          spec: {
            generate: { status: 'succeeded', updatedAt: '2026-04-03T00:00:00Z', message: null },
            confirm: { status: 'idle', updatedAt: null, message: null },
          },
        },
      },
    })

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId={taskNode.node_id}
        nodeRegistry={[initNode, taskNode]}
        variant="ask"
      />,
    )

    expect(screen.getByTestId('frame-context-action-status-row')).toBeInTheDocument()
    expect(screen.getByTestId('frame-context-action-frame')).toHaveTextContent('frame')
    expect(screen.getByTestId('frame-context-action-frame')).toHaveTextContent('Generating')
    expect(screen.getByTestId('frame-context-action-clarify')).toHaveTextContent('clarify')
    expect(screen.getByTestId('frame-context-action-clarify')).toHaveTextContent('Confirm failed')
    expect(screen.getByTestId('frame-context-action-spec')).toHaveTextContent('spec')
    expect(screen.getByTestId('frame-context-action-spec')).toHaveTextContent('Generated')
  })

  it('excludes init node from metadata shell and strips init index prefix', async () => {
    const loadDocument = seedDocumentStore('task-1')
    const loadClarify = seedClarifyStore('task-1')

    const initNode = makeNode({
      node_id: 'init',
      title: 'Workspace Init',
      node_kind: 'root',
      is_init_node: true,
      parent_id: null,
      child_ids: ['task-1'],
      hierarchical_number: '1',
    })
    const taskNode = makeNode({
      node_id: 'task-1',
      title: 'Implement Login',
      node_kind: 'original',
      is_init_node: false,
      parent_id: 'init',
      child_ids: [],
      hierarchical_number: '1.1',
      depth: 1,
    })

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId="task-1"
        nodeRegistry={[initNode, taskNode]}
        variant="ask"
      />,
    )

    expect(screen.queryByText('Workspace Init')).not.toBeInTheDocument()
    expect(screen.getByText('Implement Login')).toBeInTheDocument()
    expect(screen.queryByText('1.1')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(loadDocument).toHaveBeenCalledWith('project-1', 'task-1', 'frame')
      expect(loadClarify).toHaveBeenCalledWith('project-1', 'task-1')
    })
    expect(loadDocument).not.toHaveBeenCalledWith('project-1', 'init', 'frame')
    expect(loadClarify).not.toHaveBeenCalledWith('project-1', 'init')
  })

  it('renders local links in frame/spec context using filename line labels', async () => {
    const { initNode, taskNode } = makeTaskContext()
    const loadDocument = seedDocumentStore(taskNode.node_id, {
      frameContent: '[Frame Doc](file:///C:/workspace/project/frame.md#L74C3)',
      specContent: '[Spec Doc](file:///C:/workspace/project/spec.md#L12C8)',
    })
    const loadClarify = seedClarifyStore(taskNode.node_id)

    useProjectStore.setState({
      snapshot: {
        schema_version: 1,
        project: {
          id: 'project-1',
          name: 'Test',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project',
          created_at: '2026-04-03T00:00:00Z',
          updated_at: '2026-04-03T00:00:00Z',
        },
        tree_state: {
          root_node_id: initNode.node_id,
          active_node_id: taskNode.node_id,
          node_registry: [initNode, taskNode],
        },
        updated_at: '2026-04-03T00:00:00Z',
      },
      selectedNodeId: taskNode.node_id,
    })

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId={taskNode.node_id}
        nodeRegistry={[initNode, taskNode]}
        variant="audit"
        specConfirmed
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Frame' }))
    expect(await screen.findByText('frame.md (line 74, col 3)')).toBeInTheDocument()
    expect(screen.queryByText('Frame Doc')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Spec' }))
    expect(await screen.findByText('spec.md (line 12, col 8)')).toBeInTheDocument()
    expect(screen.queryByText('Spec Doc')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(loadDocument).toHaveBeenCalledWith('project-1', taskNode.node_id, 'frame')
    })
    await waitFor(() => {
      expect(loadClarify).toHaveBeenCalledWith('project-1', taskNode.node_id)
    })
  })

  it('uses the same document chrome for frame, clarify, and spec panels', async () => {
    const { initNode, taskNode } = makeTaskContext()
    seedDocumentStore(taskNode.node_id, {
      frameContent: '# Frame\nContent',
      specContent: '# Spec\nContent',
    })
    seedClarifyStore(taskNode.node_id)

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId={taskNode.node_id}
        nodeRegistry={[initNode, taskNode]}
        variant="audit"
        specConfirmed
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Frame' }))
    fireEvent.click(screen.getByRole('button', { name: 'Spec' }))
    fireEvent.click(screen.getByRole('button', { name: 'Clarify' }))

    expect(await screen.findByTestId('frame-context-panel-body-frame')).toHaveAttribute('data-panel-chrome', 'document')
    expect(screen.getByTestId('frame-context-panel-body-spec')).toHaveAttribute('data-panel-chrome', 'document')
    expect(screen.getByTestId('frame-context-panel-body-clarify')).toHaveAttribute('data-panel-chrome', 'document')
  })

  it('renders split panel using document chrome for ancestor nodes', async () => {
    const loadDocument = vi.fn().mockResolvedValue(undefined)
    useNodeDocumentStore.setState({
      ...useNodeDocumentStore.getState(),
      loadDocument,
      entries: {
        'project-1::parent::frame': {
          content: '# Root Frame\nParent',
          savedContent: '# Root Frame\nParent',
          updatedAt: '2026-04-03T00:00:00Z',
          isLoading: false,
          isSaving: false,
          error: null,
          hasLoaded: true,
        },
        'project-1::child::frame': {
          content: '# Child Frame\nCurrent',
          savedContent: '# Child Frame\nCurrent',
          updatedAt: '2026-04-03T00:00:00Z',
          isLoading: false,
          isSaving: false,
          error: null,
          hasLoaded: true,
        },
      },
    } as Partial<ReturnType<typeof useNodeDocumentStore.getState>>)

    const loadClarify = vi.fn().mockResolvedValue(undefined)
    useClarifyStore.setState({
      ...useClarifyStore.getState(),
      loadClarify,
      entries: {
        'project-1::parent': {
          clarify: {
            schema_version: 2,
            source_frame_revision: 1,
            confirmed_revision: 0,
            confirmed_at: null,
            questions: [],
            updated_at: '2026-04-03T00:00:00Z',
          },
          savedQuestions: [],
          isLoading: false,
          isSaving: false,
          loadError: '',
          saveError: '',
          hasLoaded: true,
        },
        'project-1::child': {
          clarify: {
            schema_version: 2,
            source_frame_revision: 1,
            confirmed_revision: 0,
            confirmed_at: null,
            questions: [],
            updated_at: '2026-04-03T00:00:00Z',
          },
          savedQuestions: [],
          isLoading: false,
          isSaving: false,
          loadError: '',
          saveError: '',
          hasLoaded: true,
        },
      },
    } as Partial<ReturnType<typeof useClarifyStore.getState>>)

    const initNode = makeNode({
      node_id: 'init',
      title: 'Workspace Init',
      node_kind: 'root',
      is_init_node: true,
      parent_id: null,
      child_ids: ['parent'],
      hierarchical_number: '1',
    })
    const parentNode = makeNode({
      node_id: 'parent',
      title: 'Parent task',
      node_kind: 'original',
      is_init_node: false,
      parent_id: 'init',
      child_ids: ['child'],
      hierarchical_number: '1.1',
      depth: 1,
    })
    const childNode = makeNode({
      node_id: 'child',
      title: 'Child task',
      node_kind: 'original',
      is_init_node: false,
      parent_id: 'parent',
      child_ids: [],
      hierarchical_number: '1.1.1',
      depth: 2,
    })

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId="child"
        nodeRegistry={[initNode, parentNode, childNode]}
        variant="ask"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Split' }))

    expect(await screen.findByTestId('frame-context-panel-body-split')).toHaveAttribute('data-panel-chrome', 'document')
    expect(screen.getByRole('heading', { level: 2, name: /child task/i })).toBeInTheDocument()
    expect(screen.getByTestId('frame-context-panel-body-split')).toHaveTextContent('Child task')
  })
})
