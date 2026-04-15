import { describe, expect, it } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import {
  askQueuePolicyAdapter,
  executionQueuePolicyAdapter,
  type AskQueueContext,
  type AskQueuePolicyState,
  type AskSendWindowOptions,
  type ExecutionQueueContext,
  type ExecutionQueuePolicyState,
  type ExecutionSendWindowOptions,
} from '../../src/features/conversation/state/threadQueuePolicyAdaptersV3'
import type { QueueCoreEntry } from '../../src/features/conversation/state/threadQueueCoreV3'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    items: [],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
    ...overrides,
  }
}

function makeExecutionEntry(overrides: Partial<QueueCoreEntry<ExecutionQueueContext>> = {}) {
  return {
    entryId: overrides.entryId ?? 'exec-1',
    text: overrides.text ?? 'queued execution message',
    idempotencyKey: overrides.idempotencyKey ?? 'idem-exec-1',
    createdAtMs: overrides.createdAtMs ?? 1_000,
    enqueueContext: overrides.enqueueContext ?? {
      latestExecutionRunId: 'run-1',
      planReadyRevision: 1,
    },
    status: overrides.status ?? ('queued' as const),
    attemptCount: overrides.attemptCount ?? 0,
    lastError: overrides.lastError ?? null,
  }
}

function makeAskEntry(overrides: Partial<QueueCoreEntry<AskQueueContext>> = {}) {
  return {
    entryId: overrides.entryId ?? 'ask-1',
    text: overrides.text ?? 'queued ask message',
    idempotencyKey: overrides.idempotencyKey ?? 'idem-ask-1',
    createdAtMs: overrides.createdAtMs ?? 1_000,
    enqueueContext: overrides.enqueueContext ?? {
      threadId: 'thread-1',
      snapshotVersion: 2,
      staleMarker: false,
    },
    status: overrides.status ?? ('queued' as const),
    attemptCount: overrides.attemptCount ?? 0,
    lastError: overrides.lastError ?? null,
  }
}

describe('threadQueuePolicyAdaptersV3', () => {
  it('maps execution pause reasons using deterministic table-driven contract cases', () => {
    const options: ExecutionSendWindowOptions = { manual: false, allowPlanReadyGate: false }
    const cases: Array<{
      name: string
      state: ExecutionQueuePolicyState
      expected: string
    }> = [
      {
        name: 'operator pause takes priority',
        state: {
          snapshot: makeSnapshot(),
          operatorPaused: true,
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
        },
        expected: 'operator_pause',
      },
      {
        name: 'runtime waiting input from processing state',
        state: {
          snapshot: makeSnapshot({ processingState: 'waiting_user_input' }),
          operatorPaused: false,
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
        },
        expected: 'runtime_waiting_input',
      },
      {
        name: 'plan-ready gate blocks queue',
        state: {
          snapshot: makeSnapshot({
            uiSignals: {
              planReady: {
                planItemId: 'plan-1',
                revision: 2,
                ready: true,
                failed: false,
              },
              activeUserInputRequests: [],
            },
          }),
          operatorPaused: false,
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
        },
        expected: 'plan_ready_gate',
      },
      {
        name: 'workflow mismatch blocks queue',
        state: {
          snapshot: makeSnapshot(),
          operatorPaused: false,
          workflowPhase: 'execution_running',
          canSendExecutionMessage: false,
        },
        expected: 'workflow_blocked',
      },
      {
        name: 'idle runtime can auto-send',
        state: {
          snapshot: makeSnapshot(),
          operatorPaused: false,
          workflowPhase: 'execution_decision_pending',
          canSendExecutionMessage: true,
        },
        expected: 'none',
      },
    ]

    for (const testCase of cases) {
      const actual = executionQueuePolicyAdapter.evaluatePauseReason(
        'execution',
        testCase.state,
        options,
      )
      expect(actual, testCase.name).toBe(testCase.expected)
    }
  })

  it('maps execution send-window behavior for manual and gated scenarios', () => {
    const baseState: ExecutionQueuePolicyState = {
      snapshot: makeSnapshot(),
      operatorPaused: false,
      workflowPhase: 'execution_decision_pending',
      canSendExecutionMessage: true,
    }

    expect(
      executionQueuePolicyAdapter.sendWindowIsOpen('execution', baseState, {
        manual: false,
        allowPlanReadyGate: false,
      }),
    ).toBe(true)

    expect(
      executionQueuePolicyAdapter.sendWindowIsOpen(
        'execution',
        { ...baseState, operatorPaused: true },
        { manual: false, allowPlanReadyGate: false },
      ),
    ).toBe(false)

    expect(
      executionQueuePolicyAdapter.sendWindowIsOpen(
        'execution',
        { ...baseState, operatorPaused: true },
        { manual: true, allowPlanReadyGate: false },
      ),
    ).toBe(true)

    const planReadyState: ExecutionQueuePolicyState = {
      ...baseState,
      snapshot: makeSnapshot({
        uiSignals: {
          planReady: {
            planItemId: 'plan-1',
            revision: 5,
            ready: true,
            failed: false,
          },
          activeUserInputRequests: [],
        },
      }),
    }
    expect(
      executionQueuePolicyAdapter.sendWindowIsOpen('execution', planReadyState, {
        manual: false,
        allowPlanReadyGate: false,
      }),
    ).toBe(false)
    expect(
      executionQueuePolicyAdapter.sendWindowIsOpen('execution', planReadyState, {
        manual: false,
        allowPlanReadyGate: true,
      }),
    ).toBe(true)
  })

  it('requires execution confirmation only on stale or context-drift conditions', () => {
    const nowMs = 100_000
    const currentContext: ExecutionQueueContext = {
      latestExecutionRunId: 'run-1',
      planReadyRevision: 1,
    }

    expect(
      executionQueuePolicyAdapter.requiresConfirmation(
        'execution',
        makeExecutionEntry({ createdAtMs: nowMs - 90_001 }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      executionQueuePolicyAdapter.requiresConfirmation(
        'execution',
        makeExecutionEntry({
          enqueueContext: {
            latestExecutionRunId: 'run-old',
            planReadyRevision: 1,
          },
        }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      executionQueuePolicyAdapter.requiresConfirmation(
        'execution',
        makeExecutionEntry({
          enqueueContext: {
            latestExecutionRunId: 'run-1',
            planReadyRevision: 9,
          },
        }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      executionQueuePolicyAdapter.requiresConfirmation(
        'execution',
        makeExecutionEntry({ createdAtMs: nowMs - 1_000 }),
        currentContext,
        nowMs,
      ),
    ).toBe(false)
  })

  it('maps ask pause reasons via A0 gating matrix contract', () => {
    const options: AskSendWindowOptions = { streamOrStateMismatch: false }
    const cases: Array<{
      name: string
      state: AskQueuePolicyState
      optionPatch?: Partial<AskSendWindowOptions>
      expected: string
    }> = [
      {
        name: 'snapshot unavailable',
        state: {
          snapshot: null,
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        expected: 'snapshot_unavailable',
      },
      {
        name: 'stream mismatch from options',
        state: {
          snapshot: makeSnapshot({ threadRole: 'ask_planning' }),
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        optionPatch: { streamOrStateMismatch: true },
        expected: 'stream_or_state_mismatch',
      },
      {
        name: 'operator pause',
        state: {
          snapshot: makeSnapshot({ threadRole: 'ask_planning' }),
          operatorPaused: true,
          streamOrStateMismatch: false,
        },
        expected: 'operator_pause',
      },
      {
        name: 'active turn running',
        state: {
          snapshot: makeSnapshot({
            threadRole: 'ask_planning',
            activeTurnId: 'turn-1',
            processingState: 'running',
          }),
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        expected: 'active_turn_running',
      },
      {
        name: 'processing waiting user input maps to active_turn_running by A0 deterministic order',
        state: {
          snapshot: makeSnapshot({
            threadRole: 'ask_planning',
            processingState: 'waiting_user_input',
            uiSignals: {
              planReady: {
                planItemId: null,
                revision: null,
                ready: false,
                failed: false,
              },
              activeUserInputRequests: [
                {
                  requestId: 'req-1',
                  itemId: 'input-1',
                  threadId: 'thread-1',
                  turnId: 'turn-1',
                  status: 'requested',
                  createdAt: '2026-04-01T00:00:00Z',
                  submittedAt: null,
                  resolvedAt: null,
                  answers: [],
                },
              ],
            },
          }),
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        expected: 'active_turn_running',
      },
      {
        name: 'pending required user input while idle maps to waiting_user_input',
        state: {
          snapshot: makeSnapshot({
            threadRole: 'ask_planning',
            processingState: 'idle',
            activeTurnId: null,
            uiSignals: {
              planReady: {
                planItemId: null,
                revision: null,
                ready: false,
                failed: false,
              },
              activeUserInputRequests: [
                {
                  requestId: 'req-1',
                  itemId: 'input-1',
                  threadId: 'thread-1',
                  turnId: 'turn-1',
                  status: 'requested',
                  createdAt: '2026-04-01T00:00:00Z',
                  submittedAt: null,
                  resolvedAt: null,
                  answers: [],
                },
              ],
            },
          }),
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        expected: 'waiting_user_input',
      },
      {
        name: 'idle ask lane is sendable',
        state: {
          snapshot: makeSnapshot({ threadRole: 'ask_planning' }),
          operatorPaused: false,
          streamOrStateMismatch: false,
        },
        expected: 'none',
      },
    ]

    for (const testCase of cases) {
      const actual = askQueuePolicyAdapter.evaluatePauseReason(
        'ask_planning',
        testCase.state,
        { ...options, ...testCase.optionPatch },
      )
      expect(actual, testCase.name).toBe(testCase.expected)
    }
  })

  it('opens ask send window only when pause reason is none', () => {
    const openState: AskQueuePolicyState = {
      snapshot: makeSnapshot({ threadRole: 'ask_planning' }),
      operatorPaused: false,
      streamOrStateMismatch: false,
    }
    const blockedState: AskQueuePolicyState = {
      snapshot: makeSnapshot({ threadRole: 'ask_planning', activeTurnId: 'turn-1' }),
      operatorPaused: false,
      streamOrStateMismatch: false,
    }

    expect(
      askQueuePolicyAdapter.sendWindowIsOpen('ask_planning', openState, {
        streamOrStateMismatch: false,
      }),
    ).toBe(true)
    expect(
      askQueuePolicyAdapter.sendWindowIsOpen('ask_planning', blockedState, {
        streamOrStateMismatch: false,
      }),
    ).toBe(false)
  })

  it('requires ask confirmation only on stale or context-drift conditions', () => {
    const nowMs = 100_000
    const currentContext: AskQueueContext = {
      threadId: 'thread-1',
      snapshotVersion: 2,
      staleMarker: false,
    }

    expect(
      askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry({ createdAtMs: nowMs - 90_001 }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry({
          enqueueContext: {
            threadId: 'thread-other',
            snapshotVersion: 2,
            staleMarker: false,
          },
        }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry({
          enqueueContext: {
            threadId: 'thread-1',
            snapshotVersion: 9,
            staleMarker: false,
          },
        }),
        currentContext,
        nowMs,
      ),
    ).toBe(true)

    expect(
      askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry(),
        { ...currentContext, staleMarker: true },
        nowMs,
      ),
    ).toBe(true)

    expect(
      askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry({ createdAtMs: nowMs - 1_000 }),
        currentContext,
        nowMs,
      ),
    ).toBe(false)
  })

  it('remains deterministic across repeated execution and ask policy evaluation', () => {
    const executionState: ExecutionQueuePolicyState = {
      snapshot: makeSnapshot(),
      operatorPaused: false,
      workflowPhase: 'execution_decision_pending',
      canSendExecutionMessage: true,
    }
    const askState: AskQueuePolicyState = {
      snapshot: makeSnapshot({ threadRole: 'ask_planning' }),
      operatorPaused: false,
      streamOrStateMismatch: false,
    }

    const executionSignature = JSON.stringify({
      pause: executionQueuePolicyAdapter.evaluatePauseReason('execution', executionState, {
        manual: false,
        allowPlanReadyGate: false,
      }),
      open: executionQueuePolicyAdapter.sendWindowIsOpen('execution', executionState, {
        manual: false,
        allowPlanReadyGate: false,
      }),
      confirm: executionQueuePolicyAdapter.requiresConfirmation(
        'execution',
        makeExecutionEntry(),
        {
          latestExecutionRunId: 'run-1',
          planReadyRevision: 1,
        },
        100_000,
      ),
    })
    const askSignature = JSON.stringify({
      pause: askQueuePolicyAdapter.evaluatePauseReason('ask_planning', askState, {
        streamOrStateMismatch: false,
      }),
      open: askQueuePolicyAdapter.sendWindowIsOpen('ask_planning', askState, {
        streamOrStateMismatch: false,
      }),
      confirm: askQueuePolicyAdapter.requiresConfirmation(
        'ask_planning',
        makeAskEntry(),
        {
          threadId: 'thread-1',
          snapshotVersion: 2,
          staleMarker: false,
        },
        100_000,
      ),
    })

    for (let index = 0; index < 25; index += 1) {
      expect(
        JSON.stringify({
          pause: executionQueuePolicyAdapter.evaluatePauseReason('execution', executionState, {
            manual: false,
            allowPlanReadyGate: false,
          }),
          open: executionQueuePolicyAdapter.sendWindowIsOpen('execution', executionState, {
            manual: false,
            allowPlanReadyGate: false,
          }),
          confirm: executionQueuePolicyAdapter.requiresConfirmation(
            'execution',
            makeExecutionEntry(),
            {
              latestExecutionRunId: 'run-1',
              planReadyRevision: 1,
            },
            100_000,
          ),
        }),
      ).toBe(executionSignature)

      expect(
        JSON.stringify({
          pause: askQueuePolicyAdapter.evaluatePauseReason('ask_planning', askState, {
            streamOrStateMismatch: false,
          }),
          open: askQueuePolicyAdapter.sendWindowIsOpen('ask_planning', askState, {
            streamOrStateMismatch: false,
          }),
          confirm: askQueuePolicyAdapter.requiresConfirmation(
            'ask_planning',
            makeAskEntry(),
            {
              threadId: 'thread-1',
              snapshotVersion: 2,
              staleMarker: false,
            },
            100_000,
          ),
        }),
      ).toBe(askSignature)
    }
  })
})
