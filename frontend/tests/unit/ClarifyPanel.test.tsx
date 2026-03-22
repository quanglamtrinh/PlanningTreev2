import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getDetailState: vi.fn().mockResolvedValue({
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
    }),
    getClarify: vi.fn(),
    updateClarify: vi.fn(),
    confirmClarify: vi.fn(),
    generateClarify: vi.fn(),
    getClarifyGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  ApiError: class extends Error {
    status: number
    code: string | null
    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  },
}))

import type { ClarifyQuestion, ClarifyState, NodeRecord } from '../../src/api/types'
import { ClarifyPanel } from '../../src/features/node/ClarifyPanel'
import { useClarifyStore } from '../../src/stores/clarify-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'

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

const TWO_QUESTIONS: ClarifyQuestion[] = [
  {
    field_name: 'target_platform',
    question: "What should 'target_platform' be for this task?",
    why_it_matters: 'Affects build tooling',
    current_value: '',
    options: [
      { id: 'web', label: 'Web', value: 'Web', rationale: 'Standard', recommended: true },
      { id: 'mobile', label: 'Mobile', value: 'Mobile', rationale: 'Mobile first', recommended: false },
    ],
    selected_option_id: null,
    custom_answer: '',
    allow_custom: true,
  },
  {
    field_name: 'storage_level',
    question: "What should 'storage_level' be for this task?",
    why_it_matters: 'Affects persistence model',
    current_value: '',
    options: [
      { id: 'local', label: 'Local', value: 'Local', rationale: 'Simple', recommended: true },
      { id: 'cloud', label: 'Cloud', value: 'Cloud', rationale: 'Scalable', recommended: false },
    ],
    selected_option_id: null,
    custom_answer: '',
    allow_custom: true,
  },
]

const CLARIFY_STATE: ClarifyState = {
  schema_version: 2,
  source_frame_revision: 1,
  confirmed_revision: 0,
  confirmed_at: null,
  questions: TWO_QUESTIONS,
  updated_at: null,
}

function seedStore(questions: ClarifyQuestion[] = TWO_QUESTIONS) {
  useClarifyStore.setState({
    entries: {
      'p1::root': {
        clarify: { ...CLARIFY_STATE, questions: questions.map((q) => ({ ...q })) },
        savedQuestions: questions.map((q) => ({ ...q })),
        isLoading: false,
        isSaving: false,
        loadError: '',
        saveError: '',
        hasLoaded: true,
      },
    },
  })
}

describe('ClarifyPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useClarifyStore.getState().reset()
    useDetailStateStore.getState().reset()
    apiMock.getClarifyGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
  })

  // ── Debounce-controlled tests (fake timers, pre-seeded store) ──

  describe('save and debounce behavior', () => {
    beforeEach(() => {
      vi.useFakeTimers()
      seedStore()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('shows save error banner when updateClarify fails', async () => {
      apiMock.updateClarify.mockRejectedValue(new Error('Network timeout'))

      render(<ClarifyPanel projectId="p1" node={makeNode()} />)

      const textarea = screen.getByLabelText('Custom answer for: target_platform')
      await act(async () => {
        fireEvent.change(textarea, { target: { value: 'web' } })
      })

      await act(async () => {
        await vi.advanceTimersByTimeAsync(900)
      })

      expect(screen.getByTestId('save-error-clarify')).toHaveTextContent('Network timeout')
    })

    it('rolls back the draft to saved state on save failure', async () => {
      apiMock.updateClarify.mockRejectedValue(new Error('save failed'))

      render(<ClarifyPanel projectId="p1" node={makeNode()} />)

      const textarea = screen.getByLabelText('Custom answer for: target_platform')

      await act(async () => {
        fireEvent.change(textarea, { target: { value: 'mobile' } })
      })
      expect(textarea).toHaveValue('mobile')

      await act(async () => {
        await vi.advanceTimersByTimeAsync(900)
      })

      // After rollback, value should revert to the original (empty)
      expect(textarea).toHaveValue('')
    })

    it('debounces save — does not call API on every keystroke', async () => {
      apiMock.updateClarify.mockResolvedValue(CLARIFY_STATE)

      render(<ClarifyPanel projectId="p1" node={makeNode()} />)

      const textarea = screen.getByLabelText('Custom answer for: target_platform')

      await act(async () => {
        fireEvent.change(textarea, { target: { value: 'w' } })
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200)
      })
      await act(async () => {
        fireEvent.change(textarea, { target: { value: 'we' } })
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200)
      })
      await act(async () => {
        fireEvent.change(textarea, { target: { value: 'web' } })
      })

      // API should not have been called yet (still within debounce window)
      expect(apiMock.updateClarify).not.toHaveBeenCalled()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(900)
      })

      expect(apiMock.updateClarify).toHaveBeenCalledTimes(1)
      // The single call should contain the final custom_answer value
      expect(apiMock.updateClarify).toHaveBeenCalledWith('p1', 'root', [
        expect.objectContaining({ field_name: 'target_platform', custom_answer: 'web' }),
      ])
    })

    it('confirmClarify aborts when flush fails — confirm button stays disabled', async () => {
      apiMock.updateClarify.mockRejectedValue(new Error('save failed'))
      apiMock.confirmClarify.mockResolvedValue({
        node_id: 'root',
        frame_confirmed: true,
        frame_confirmed_revision: 1,
        frame_revision: 1,
        clarify_unlocked: true,
        clarify_stale: false,
        clarify_confirmed: true,
        spec_unlocked: true,
        spec_stale: false,
        spec_confirmed: false,
      })

      render(<ClarifyPanel projectId="p1" node={makeNode()} />)

      // Make changes so there's a dirty draft
      await act(async () => {
        fireEvent.change(screen.getByLabelText('Custom answer for: target_platform'), {
          target: { value: 'web' },
        })
      })
      await act(async () => {
        fireEvent.change(screen.getByLabelText('Custom answer for: storage_level'), {
          target: { value: 'local' },
        })
      })

      // Flush triggers and fails → rollback to original state
      await act(async () => {
        await vi.advanceTimersByTimeAsync(900)
      })

      // After rollback, questions are unresolved, so confirm is disabled
      expect(screen.getByTestId('confirm-clarify')).toBeDisabled()
      // confirmClarify should NOT have been called
      expect(apiMock.confirmClarify).not.toHaveBeenCalled()
    })

    it('flushes dirty drafts then confirms when user clicks Confirm', async () => {
      const answeredState: ClarifyState = {
        ...CLARIFY_STATE,
        questions: TWO_QUESTIONS.map((q) => ({
          ...q,
          custom_answer: q.field_name === 'target_platform' ? 'web' : 'local',
        })),
      }
      apiMock.updateClarify.mockResolvedValue(answeredState)
      apiMock.confirmClarify.mockResolvedValue({
        node_id: 'root',
        frame_confirmed: true,
        frame_confirmed_revision: 1,
        frame_revision: 1,
        clarify_unlocked: true,
        clarify_stale: false,
        clarify_confirmed: true,
        spec_unlocked: true,
        spec_stale: false,
        spec_confirmed: false,
      })

      render(<ClarifyPanel projectId="p1" node={makeNode()} />)

      // Answer both questions via custom_answer
      await act(async () => {
        fireEvent.change(screen.getByLabelText('Custom answer for: target_platform'), {
          target: { value: 'web' },
        })
      })
      await act(async () => {
        fireEvent.change(screen.getByLabelText('Custom answer for: storage_level'), {
          target: { value: 'local' },
        })
      })

      // Flush the debounce so the save goes through
      await act(async () => {
        await vi.advanceTimersByTimeAsync(900)
      })

      expect(apiMock.updateClarify).toHaveBeenCalledTimes(1)

      // Confirm button should be enabled now
      const confirmBtn = screen.getByTestId('confirm-clarify')
      expect(confirmBtn).not.toBeDisabled()

      await act(async () => {
        fireEvent.click(confirmBtn)
      })

      // flushAnswers is called again (no-op since nothing dirty), then confirmClarify
      expect(apiMock.confirmClarify).toHaveBeenCalledWith('p1', 'root')
    })
  })

  // ── Tests that don't need debounce control (real timers) ──

  it('shows confirm error when confirmClarify API fails', async () => {
    const answeredQuestions = TWO_QUESTIONS.map((q) => ({
      ...q,
      selected_option_id: q.options[0]?.id ?? null,
    }))
    apiMock.getClarify.mockResolvedValue({
      ...CLARIFY_STATE,
      questions: answeredQuestions,
    })
    apiMock.confirmClarify.mockRejectedValue(new Error('Server error'))

    render(<ClarifyPanel projectId="p1" node={makeNode()} />)

    await waitFor(() => {
      expect(screen.getByTestId('confirm-clarify')).not.toBeDisabled()
    })

    fireEvent.click(screen.getByTestId('confirm-clarify'))

    await waitFor(() => {
      expect(screen.getByTestId('confirm-error-clarify')).toHaveTextContent('Server error')
    })
  })
})
