import { act, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAskSidecarStream } from '../../src/api/hooks'
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
  useAskSidecarStream(projectId, nodeId)
  return null
}

function mockEventSources(): MockEventSourceInstance[] {
  return (globalThis.EventSource as unknown as { instances: MockEventSourceInstance[] }).instances
}

describe('useAskSidecarStream', () => {
  beforeEach(() => {
    useAskStore.setState(useAskStore.getInitialState())
  })

  it('buffers packet events until initial sidecar load completes and closes on unmount', async () => {
    let resolveLoad: (() => void) | null = null
    const loadSidecar = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveLoad = () => {
            useAskStore.setState({
              sidecar: {
                projectId: 'project-1',
                nodeId: 'node-1',
                eventSeq: 2,
                packetList: [],
              },
            })
            resolve()
          }
        }),
    )
    useAskStore.setState({ ...useAskStore.getInitialState(), loadSidecar })

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

    expect(useAskStore.getState().sidecar).toBeNull()

    await act(async () => {
      resolveLoad?.()
    })

    await waitFor(() => {
      expect(useAskStore.getState().sidecar?.eventSeq).toBe(3)
    })
    expect(useAskStore.getState().sidecar?.packetList).toHaveLength(1)

    view.unmount()

    expect(eventSource.readyState).toBe(2)
    expect(useAskStore.getState().sidecar).toBeNull()
  })

  it('reloads ask sidecar on reconnect and ignores transcript-only events', async () => {
    let reconnectResolve: (() => void) | null = null
    const loadSidecar = vi
      .fn<() => Promise<void>>()
      .mockImplementationOnce(async () => {
        useAskStore.setState({
          sidecar: {
            projectId: 'project-1',
            nodeId: 'node-1',
            eventSeq: 2,
            packetList: [],
          },
        })
      })
      .mockImplementationOnce(
        () =>
          new Promise<void>((resolve) => {
            reconnectResolve = () => {
              useAskStore.setState({
                sidecar: {
                  projectId: 'project-1',
                  nodeId: 'node-1',
                  eventSeq: 4,
                  packetList: [],
                },
              })
              resolve()
            }
          }),
      )
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      loadSidecar,
    })

    render(<HookHarness projectId="project-1" nodeId="node-1" />)
    const [eventSource] = mockEventSources()

    await waitFor(() => {
      expect(useAskStore.getState().sidecar?.eventSeq).toBe(2)
    })

    act(() => {
      eventSource.emitOpen()
      eventSource.emitError()
      eventSource.emitOpen()
      eventSource.emitMessage(
        JSON.stringify({
          type: 'ask_message_created',
          event_seq: 3,
          active_turn_id: 'turn_1',
          user_message: {
            message_id: 'msg_user',
            role: 'user',
            content: 'hello',
            status: 'completed',
            created_at: '2026-03-10T00:00:00Z',
            updated_at: '2026-03-10T00:00:00Z',
            error: null,
          },
          assistant_message: {
            message_id: 'msg_assistant',
            role: 'assistant',
            content: '',
            status: 'pending',
            created_at: '2026-03-10T00:00:00Z',
            updated_at: '2026-03-10T00:00:00Z',
            error: null,
          },
        } satisfies AskEvent),
      )
      eventSource.emitMessage(
        JSON.stringify({
          type: 'ask_packet_status_changed',
          event_seq: 5,
          packet: {
            packet_id: 'packet-1',
            node_id: 'node-1',
            created_at: '2026-03-10T00:00:00Z',
            source_message_ids: [],
            summary: 'Risk',
            context_text: 'Key risk',
            status: 'approved',
            status_reason: null,
            merged_at: null,
            merged_planning_turn_id: null,
            suggested_by: 'agent',
          },
        } satisfies AskEvent),
      )
    })

    expect(useAskStore.getState().sidecar?.eventSeq).toBe(2)

    await act(async () => {
      reconnectResolve?.()
    })

    await waitFor(() => {
      expect(useAskStore.getState().sidecar?.eventSeq).toBe(5)
    })
    expect(useAskStore.getState().sidecar?.packetList[0]?.status).toBe('approved')
  })

  it('clears ask sidecar when projectId or nodeId becomes null', async () => {
    useAskStore.setState({
      ...useAskStore.getInitialState(),
      sidecar: {
        projectId: 'project-1',
        nodeId: 'node-1',
        eventSeq: 2,
        packetList: [],
      },
    })

    const view = render(<HookHarness projectId="project-1" nodeId="node-1" />)
    view.rerender(<HookHarness projectId={null} nodeId={null} />)

    await waitFor(() => {
      expect(useAskStore.getState().sidecar).toBeNull()
    })
  })
})
