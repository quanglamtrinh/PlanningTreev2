import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AskFollowupQueuePanelV2 } from '../../src/features/conversation/components/AskFollowupQueuePanelV2'
import { BreadcrumbThreadTabsV2 } from '../../src/features/conversation/components/BreadcrumbThreadTabsV2'
import { ExecutionFollowupQueuePanelV2 } from '../../src/features/conversation/components/ExecutionFollowupQueuePanelV2'
import type {
  ThreadAskFollowupQueueActions,
  ThreadAskFollowupQueueState,
  ThreadExecutionFollowupQueueActions,
  ThreadExecutionFollowupQueueState,
} from '../../src/features/conversation/state/threadByIdStoreV3'

function makeExecutionState(
  overrides: Partial<ThreadExecutionFollowupQueueState> = {},
): ThreadExecutionFollowupQueueState {
  return {
    activeThreadRole: 'execution',
    executionFollowupQueue: [],
    executionQueuePauseReason: 'none',
    executionQueueOperatorPaused: false,
    isSending: false,
    ...overrides,
  }
}

function makeExecutionActions(): Pick<
  ThreadExecutionFollowupQueueActions,
  'removeQueued' | 'reorderQueued' | 'sendQueuedNow' | 'confirmQueued' | 'retryQueued' | 'setOperatorPause'
> {
  return {
    removeQueued: vi.fn(),
    reorderQueued: vi.fn(),
    sendQueuedNow: vi.fn().mockResolvedValue(undefined),
    confirmQueued: vi.fn().mockResolvedValue(undefined),
    retryQueued: vi.fn().mockResolvedValue(undefined),
    setOperatorPause: vi.fn(),
  }
}

function makeAskState(
  overrides: Partial<ThreadAskFollowupQueueState> = {},
): ThreadAskFollowupQueueState {
  return {
    activeThreadRole: 'ask_planning',
    askFollowupQueueEnabled: true,
    askFollowupQueue: [],
    askQueuePauseReason: 'none',
    isSending: false,
    ...overrides,
  }
}

function makeAskActions(): Pick<
  ThreadAskFollowupQueueActions,
  'removeQueued' | 'reorderAskQueued' | 'sendAskQueuedNow' | 'confirmQueued' | 'retryAskQueued'
> {
  return {
    removeQueued: vi.fn(),
    reorderAskQueued: vi.fn(),
    sendAskQueuedNow: vi.fn().mockResolvedValue(undefined),
    confirmQueued: vi.fn().mockResolvedValue(undefined),
    retryAskQueued: vi.fn().mockResolvedValue(undefined),
  }
}

describe('BreadcrumbThreadTabsV2', () => {
  it('renders active tab and calls onThreadTabChange', () => {
    const onThreadTabChange = vi.fn()

    render(<BreadcrumbThreadTabsV2 threadTab="execution" onThreadTabChange={onThreadTabChange} />)

    expect(screen.getByTestId('breadcrumb-thread-tab-execution')).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('breadcrumb-thread-tab-ask')).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByTestId('breadcrumb-thread-tab-audit')).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByTestId('breadcrumb-thread-tab-package')).toHaveAttribute('aria-selected', 'false')

    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-ask'))
    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-audit'))
    fireEvent.click(screen.getByTestId('breadcrumb-thread-tab-package'))

    expect(onThreadTabChange).toHaveBeenNthCalledWith(1, 'ask')
    expect(onThreadTabChange).toHaveBeenNthCalledWith(2, 'audit')
    expect(onThreadTabChange).toHaveBeenNthCalledWith(3, 'package')
  })
})

describe('ExecutionFollowupQueuePanelV2', () => {
  it('renders empty state and toggles operator pause', () => {
    const actions = makeExecutionActions()

    render(
      <ExecutionFollowupQueuePanelV2
        executionQueueState={makeExecutionState({ executionQueuePauseReason: 'plan_ready_gate' })}
        executionQueueActions={actions}
      />,
    )

    expect(screen.getByTestId('execution-followup-queue-panel')).toBeInTheDocument()
    expect(screen.getByText('Paused: plan-ready gate')).toBeInTheDocument()
    expect(screen.getByText('No queued follow-ups.')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('execution-followup-operator-pause-toggle'))
    expect(actions.setOperatorPause).toHaveBeenCalledWith(true)
  })

  it('dispatches queue actions and preserves disabled rules', () => {
    const actions = makeExecutionActions()
    const state = makeExecutionState({
      executionFollowupQueue: [
        {
          entryId: 'entry-1',
          text: 'queued first',
          idempotencyKey: 'idem-1',
          createdAtMs: Date.now(),
          enqueueContext: {
            latestExecutionRunId: 'run-1',
            planReadyRevision: null,
          },
          status: 'queued',
          attemptCount: 0,
          lastError: null,
        },
        {
          entryId: 'entry-2',
          text: 'needs confirmation',
          idempotencyKey: 'idem-2',
          createdAtMs: Date.now(),
          enqueueContext: {
            latestExecutionRunId: 'run-1',
            planReadyRevision: null,
          },
          status: 'requires_confirmation',
          attemptCount: 0,
          lastError: null,
        },
      ],
    })

    render(<ExecutionFollowupQueuePanelV2 executionQueueState={state} executionQueueActions={actions} />)

    const items = screen.getAllByRole('listitem')
    const firstItem = items[0]
    const secondItem = items[1]

    expect(within(firstItem).getByRole('button', { name: 'Move up' })).toBeDisabled()

    fireEvent.click(within(firstItem).getByRole('button', { name: 'Move down' }))
    fireEvent.click(within(firstItem).getByRole('button', { name: 'Send now' }))
    fireEvent.click(within(firstItem).getByRole('button', { name: 'Remove' }))
    fireEvent.click(within(secondItem).getByRole('button', { name: 'Confirm' }))

    expect(actions.reorderQueued).toHaveBeenCalledWith(0, 1)
    expect(actions.sendQueuedNow).toHaveBeenCalledWith('entry-1')
    expect(actions.removeQueued).toHaveBeenCalledWith('entry-1')
    expect(actions.confirmQueued).toHaveBeenCalledWith('entry-2')
  })
})

describe('AskFollowupQueuePanelV2', () => {
  it('renders queue reasons and dispatches ask actions with send-now restrictions', () => {
    const actions = makeAskActions()
    const state = makeAskState({
      askQueuePauseReason: 'requires_confirmation',
      askFollowupQueue: [
        {
          entryId: 'ask-blocked-1',
          text: 'blocked ask',
          idempotencyKey: 'ask-idem-blocked-1',
          createdAtMs: Date.now(),
          enqueueContext: {
            threadId: 'ask-thread-1',
            snapshotVersion: 2,
            staleMarker: false,
          },
          status: 'requires_confirmation',
          attemptCount: 0,
          lastError: null,
          confirmationReason: 'thread_drift',
        },
        {
          entryId: 'ask-queued-2',
          text: 'queued ask',
          idempotencyKey: 'ask-idem-queued-2',
          createdAtMs: Date.now(),
          enqueueContext: {
            threadId: 'ask-thread-1',
            snapshotVersion: 2,
            staleMarker: false,
          },
          status: 'queued',
          attemptCount: 0,
          lastError: null,
          confirmationReason: null,
        },
      ],
    })

    render(<AskFollowupQueuePanelV2 askQueueState={state} askQueueActions={actions} />)

    expect(screen.getByTestId('ask-followup-queue-panel')).toBeInTheDocument()
    expect(screen.getByText('Paused: confirmation required')).toBeInTheDocument()
    expect(screen.getByText('Thread context changed. Confirm before sending.')).toBeInTheDocument()

    const items = screen.getAllByRole('listitem')
    const blockedHead = items[0]
    const queuedTail = items[1]

    expect(within(blockedHead).getByRole('button', { name: 'Send now' })).toBeDisabled()
    expect(within(queuedTail).getByRole('button', { name: 'Send now' })).toBeDisabled()

    fireEvent.click(within(blockedHead).getByRole('button', { name: 'Move down' }))
    fireEvent.click(within(blockedHead).getByRole('button', { name: 'Confirm' }))
    fireEvent.click(within(blockedHead).getByRole('button', { name: 'Remove' }))

    expect(actions.reorderAskQueued).toHaveBeenCalledWith(0, 1)
    expect(actions.confirmQueued).toHaveBeenCalledWith('ask-blocked-1')
    expect(actions.removeQueued).toHaveBeenCalledWith('ask-blocked-1')
  })
})
