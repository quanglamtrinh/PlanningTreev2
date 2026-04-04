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

function seedDocumentStore() {
  const loadDocument = vi.fn().mockResolvedValue(undefined)
  useNodeDocumentStore.setState({
    ...useNodeDocumentStore.getState(),
    loadDocument,
    entries: {
      'project-1::root::frame': {
        content: '# Frame\nLogin flow',
        savedContent: '# Frame\nLogin flow',
        updatedAt: '2026-04-03T00:00:00Z',
        isLoading: false,
        isSaving: false,
        error: null,
        hasLoaded: true,
      },
      'project-1::root::spec': {
        content: '# Spec\nAuth details',
        savedContent: '# Spec\nAuth details',
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

function seedClarifyStore() {
  const loadClarify = vi.fn().mockResolvedValue(undefined)
  useClarifyStore.setState({
    ...useClarifyStore.getState(),
    loadClarify,
    entries: {
      'project-1::root': {
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
  })

  it('shows frame and clarify context even when shaping is not frozen', async () => {
    const loadDocument = seedDocumentStore()
    const loadClarify = seedClarifyStore()

    render(
      <FrameContextFeedBlock
        projectId="project-1"
        nodeId="root"
        nodeRegistry={[makeNode()]}
        variant="ask"
      />,
    )

    expect(screen.queryByText(/Frame context will appear once clarify is confirmed/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Frame' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clarify' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clarify' }))
    await waitFor(() => {
      expect(
        screen.getByText(/^1\.\s*What auth provider\?$/i, {
          selector: 'span',
        }),
      ).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(loadDocument).toHaveBeenCalledWith('project-1', 'root', 'frame')
    })
    await waitFor(() => {
      expect(loadClarify).toHaveBeenCalledWith('project-1', 'root')
    })
  })

  it('renders action status chips from shared action state', () => {
    seedDocumentStore()
    seedClarifyStore()

    const key = askShellNodeActionStateKey('project-1', 'root')
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
        nodeId="root"
        nodeRegistry={[makeNode()]}
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
})
