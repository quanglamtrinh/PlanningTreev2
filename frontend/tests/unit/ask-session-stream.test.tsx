import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAskSessionStream } from '../../src/api/hooks'
import type { AskEvent, AskSession } from '../../src/api/types'
import { useAskStore } from '../../src/stores/ask-store'

type MockEventSourceInstance = {
  readyState: number
  close: () => void
  emitOpen: () => void
  emitError: () => void
  emitMessage: (data: string) => void
}

function makeSession(overrides: Partial<AskSession> = {}): AskSession {
  return {
    project_id: 'project-1',
    node_id: 'node-1',
    active_turn_id: null,
    event_seq: 0,
    status: null,
    messages: [],
    delta_context_packets: [],
    ...overrides,
  }
}

function HookHarness({ projectId, nodeId }: { projectId: string | null; nodeId: string | null }) {
  useAskSessionStream(projectId, nodeId)
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useAskSessionStream', () => {
  beforeEach(() => {
    useAskStore.setState(useAskStore.getInitialState())
  })

  it('buffers ask events until initial session load completes and closes on unmount', async () => {
    let resolveLoad: (() => void) | null = null
    const loadSession = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveLoad = () => {
            useAskStore.setState({ session: makeSession({ event_seq: 2 }) })
            resolve()
          }
        }),
    )
    useAskStore.setState({ ...useAskStore.getInitialState(), loadSession })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    act(() => {
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'ask_delta_context_suggested',
          event_seq: 3,
          packet: {
            packet_id: 'packet-1',
            node_id: 'node-1',
            created_at: '2026-03-10T00:00:00Z',
            source_message_ids: ['msg-user', 'msg-assistant'],
            summary: 'Risk',
            context_text: 'Key risk',
            status: 'pending',
            status_reason: null,
            merged_at: null,
            merged_planning_turn_id: null,
            suggested_by: 'agent',
          },
        } satisfies AskEvent),
      )
    })

    expect(useAskStore.getState().session).toBeNull()

    await act(async () => {
      resolveLoad?.()
    })

    await waitFor(() => {
      expect(useAskStore.getState().session?.event_seq).toBe(3)
    })
    expect(useAskStore.getState().session?.delta_context_packets).toHaveLength(1)

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useAskStore.getState().session).toBeNull()
  })

  it('reloads ask session on reconnect, buffers in-flight events, and ignores stale sequences', async () => {
    let reconnectResolve: (() => void) | null = null
    const loadSession = vi
      .fn<() => Promise<void>>()
      .mockImplementationOnce(async () => {
        useAskStore.setState({ session: makeSession({ event_seq: 2 }) })
      })
      .mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            reconnectResolve = () => {
              useAskStore.setState({ session: makeSession({ event_seq: 4 }) })
              resolve()
            }
          }),
      )
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      composerDraft: 'keep me',
      loadSession,
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    await waitFor(() => {
      expect(useAskStore.getState().session?.event_seq).toBe(2)
    })

    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'ask_session_reset',
          event_seq: 3,
          session: makeSession({ event_seq: 3 }),
        } satisfies AskEvent),
      )
      eventSource.emitMessage(
        JSON.stringify({
          type: 'ask_session_reset',
          event_seq: 5,
          session: makeSession({ event_seq: 5, status: 'idle' }),
        } satisfies AskEvent),
      )
    })

    expect(useAskStore.getState().composerDraft).toBe('keep me')
    expect(useAskStore.getState().session).toBeNull()

    await act(async () => {
      reconnectResolve?.()
    })

    await waitFor(() => {
      expect(useAskStore.getState().session?.event_seq).toBe(5)
    })
    expect(useAskStore.getState().session?.status).toBe('idle')
  })

  it('clears ask session when projectId or nodeId becomes null', async () => {
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      session: makeSession({ event_seq: 2 }),
      composerDraft: 'draft',
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" />)
    view.rerender(<HookHarness projectId={null} nodeId={null} />)

    await waitFor(() => {
      expect(useAskStore.getState().session).toBeNull()
    })
    expect(useAskStore.getState().composerDraft).toBe('')
  })
})
