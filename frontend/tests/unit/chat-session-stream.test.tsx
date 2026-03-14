import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatSessionStream } from '../../src/api/hooks'
import type { ChatEvent, ChatSession } from '../../src/api/types'
import { useChatStore } from '../../src/stores/chat-store'

type MockEventSourceInstance = {
  readyState: number
  close: () => void
  emitOpen: () => void
  emitError: () => void
  emitMessage: (data: string) => void
}

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    project_id: 'project-1',
    node_id: 'node-1',
    thread_id: null,
    active_turn_id: null,
    event_seq: 0,
    config: {
      access_mode: 'project_write',
      cwd: 'C:/workspace/project',
      writable_roots: ['C:/workspace/project'],
      timeout_sec: 120,
    },
    messages: [],
    ...overrides,
  }
}

function HookHarness({ projectId, nodeId }: { projectId: string | null; nodeId: string | null }) {
  useChatSessionStream(projectId, nodeId)
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useChatSessionStream', () => {
  beforeEach(() => {
    useChatStore.setState(useChatStore.getInitialState())
  })

  it('buffers events until the initial session load completes and closes on unmount', async () => {
    let resolveLoad: (() => void) | null = null
    const loadSession = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveLoad = () => {
            useChatStore.setState({ session: makeSession({ event_seq: 3 }) })
            resolve()
          }
        }),
    )
    useChatStore.setState({ ...useChatStore.getInitialState(), loadSession })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    expect(loadSession).toHaveBeenCalledWith('project-1', 'node-1')

    act(() => {
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'message_created',
          event_seq: 4,
          active_turn_id: 'turn_1',
          user_message: {
            message_id: 'msg_user',
            role: 'user',
            content: 'hello',
            status: 'completed',
            created_at: '2026-03-08T00:00:00Z',
            updated_at: '2026-03-08T00:00:00Z',
            error: null,
          },
          assistant_message: {
            message_id: 'msg_assistant',
            role: 'assistant',
            content: '',
            status: 'pending',
            created_at: '2026-03-08T00:00:00Z',
            updated_at: '2026-03-08T00:00:00Z',
            error: null,
          },
        } satisfies ChatEvent),
      )
    })

    expect(useChatStore.getState().session).toBeNull()

    await act(async () => {
      resolveLoad?.()
    })

    await waitFor(() => {
      expect(useChatStore.getState().session?.event_seq).toBe(4)
    })
    expect(useChatStore.getState().session?.messages).toHaveLength(2)

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useChatStore.getState().session).toBeNull()
  })

  it('reloads on reconnect, buffers in-flight events, and ignores stale sequences', async () => {
    let reconnectResolve: (() => void) | null = null
    const loadSession = vi
      .fn<() => Promise<void>>()
      .mockImplementationOnce(async () => {
        useChatStore.setState({ session: makeSession({ event_seq: 2 }) })
      })
      .mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            reconnectResolve = () => {
              useChatStore.setState({ session: makeSession({ event_seq: 5 }) })
              resolve()
            }
          }),
      )
    useChatStore.setState({
      ...useChatStore.getInitialState(),
      composerDraft: 'keep me',
      loadSession,
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    await waitFor(() => {
      expect(useChatStore.getState().session?.event_seq).toBe(2)
    })

    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'session_reset',
          event_seq: 4,
          session: makeSession({ event_seq: 4, thread_id: 'stale' }),
        } satisfies ChatEvent),
      )
      eventSource.emitMessage(
        JSON.stringify({
          type: 'session_reset',
          event_seq: 6,
          session: makeSession({ event_seq: 6, thread_id: 'thread_2' }),
        } satisfies ChatEvent),
      )
    })

    expect(useChatStore.getState().composerDraft).toBe('keep me')
    expect(useChatStore.getState().session).toBeNull()

    await act(async () => {
      reconnectResolve?.()
    })

    await waitFor(() => {
      expect(useChatStore.getState().session?.event_seq).toBe(6)
    })
    expect(useChatStore.getState().session?.thread_id).toBe('thread_2')
  })
})
