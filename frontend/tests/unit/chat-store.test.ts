import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getChatSession: vi.fn(),
    sendChatMessage: vi.fn(),
    resetChatSession: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: {
    ...apiMock,
    getBootstrapStatus: vi.fn(),
    getWorkspaceSettings: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
    getSnapshot: vi.fn(),
    resetProjectToRoot: vi.fn(),
    setActiveNode: vi.fn(),
    createChild: vi.fn(),
    splitNode: vi.fn(),
    getSplitStatus: vi.fn(),
    updateNode: vi.fn(),
    setWorkspaceRoot: vi.fn(),
    deleteProject: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    code: string | null
    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  },
  buildChatEventsUrl: (projectId: string, nodeId: string, threadRole = 'ask_planning') =>
    `/v1/projects/${projectId}/nodes/${nodeId}/chat/events?thread_role=${threadRole}`,
  appendAuthToken: (url: string) => url,
}))

// Mock EventSource
class MockEventSource {
  url: string
  listeners: Record<string, ((e: { data: string }) => void)[]> = {}
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(event: string, fn: (e: { data: string }) => void) {
    if (!this.listeners[event]) this.listeners[event] = []
    this.listeners[event].push(fn)
  }

  close() {
    MockEventSource.closedCount++
  }

  emit(event: string, data: unknown) {
    for (const fn of this.listeners[event] ?? []) {
      fn({ data: JSON.stringify(data) })
    }
  }

  static instances: MockEventSource[] = []
  static closedCount = 0
  static reset() {
    MockEventSource.instances = []
    MockEventSource.closedCount = 0
  }
}

vi.stubGlobal('EventSource', MockEventSource)

import { useChatStore, applyChatEvent } from '../../src/stores/chat-store'
import type { ChatSession } from '../../src/api/types'
import { useDetailStateStore } from '../../src/stores/detail-state-store'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    thread_id: null,
    thread_role: 'ask_planning',
    active_turn_id: null,
    messages: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('chat-store', () => {
  beforeEach(() => {
    vi.useRealTimers()
    MockEventSource.reset()
    useChatStore.getState().disconnect()
    useDetailStateStore.getState().reset()
    vi.clearAllMocks()
  })

  it('loadSession fetches and sets state', async () => {
    const session = makeSession()
    apiMock.getChatSession.mockResolvedValue(session)

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    const state = useChatStore.getState()
    expect(state.session).toEqual(session)
    expect(state.activeProjectId).toBe('p1')
    expect(state.activeNodeId).toBe('n1')
    expect(state.activeThreadRole).toBe('ask_planning')
    expect(state.isLoading).toBe(false)
    expect(apiMock.getChatSession).toHaveBeenCalledWith('p1', 'n1', 'ask_planning')
  })

  it('loads role-specific sessions and opens a role-scoped event stream', async () => {
    apiMock.getChatSession.mockResolvedValue(
      makeSession({ thread_role: 'audit' }),
    )

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1', 'audit')
    })

    expect(useChatStore.getState().activeThreadRole).toBe('audit')
    expect(apiMock.getChatSession).toHaveBeenCalledWith('p1', 'n1', 'audit')
    expect(MockEventSource.instances[0]?.url).toContain('thread_role=audit')
  })

  it('sendMessage uses server-returned canonical messages', async () => {
    const session = makeSession()
    apiMock.getChatSession.mockResolvedValue(session)

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    const userMsg = {
      message_id: 'msg-1',
      role: 'user',
      content: 'Hello',
      status: 'completed',
      error: null,
      turn_id: 'turn-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const assistantMsg = {
      message_id: 'msg-2',
      role: 'assistant',
      content: '',
      status: 'pending',
      error: null,
      turn_id: 'turn-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }

    apiMock.sendChatMessage.mockResolvedValue({
      user_message: userMsg,
      assistant_message: assistantMsg,
      active_turn_id: 'turn-1',
    })

    await act(async () => {
      await useChatStore.getState().sendMessage('Hello')
    })

    const state = useChatStore.getState()
    expect(state.session?.messages).toHaveLength(2)
    expect(state.session?.messages[0]).toEqual(userMsg)
    expect(state.session?.active_turn_id).toBe('turn-1')
  })

  it('refreshes detail-state after a successful audit send', async () => {
    const refreshSpy = vi.spyOn(
      useDetailStateStore.getState(),
      'refreshExecutionState',
    ).mockResolvedValue(undefined)

    apiMock.getChatSession.mockResolvedValue(
      makeSession({ thread_role: 'audit' }),
    )
    apiMock.sendChatMessage.mockResolvedValue({
      user_message: {
        message_id: 'msg-1',
        role: 'user',
        content: 'Review this change',
        status: 'completed',
        error: null,
        turn_id: 'turn-1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      assistant_message: {
        message_id: 'msg-2',
        role: 'assistant',
        content: '',
        status: 'pending',
        error: null,
        turn_id: 'turn-1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      active_turn_id: 'turn-1',
    })

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1', 'audit')
      await useChatStore.getState().sendMessage('Review this change')
    })

    expect(refreshSpy).toHaveBeenCalledWith('p1', 'n1')
    refreshSpy.mockRestore()
  })

  it('disconnect closes EventSource', async () => {
    apiMock.getChatSession.mockResolvedValue(makeSession())

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    expect(MockEventSource.instances).toHaveLength(1)
    const closedBefore = MockEventSource.closedCount

    act(() => {
      useChatStore.getState().disconnect()
    })

    expect(MockEventSource.closedCount).toBe(closedBefore + 1)
  })

  it('ignores stale loadSession results when node changes quickly', async () => {
    const first = deferred<ChatSession>()
    const second = deferred<ChatSession>()

    apiMock.getChatSession
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const firstLoad = useChatStore.getState().loadSession('p1', 'n1')
    const secondLoad = useChatStore.getState().loadSession('p1', 'n2')

    await act(async () => {
      second.resolve(makeSession({ created_at: 'session-2' }))
      await secondLoad
    })

    await act(async () => {
      first.resolve(makeSession({ created_at: 'session-1' }))
      await firstLoad
    })

    const state = useChatStore.getState()
    expect(state.activeNodeId).toBe('n2')
    expect(state.session?.created_at).toBe('session-2')
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0]?.url).toContain('/nodes/n2/chat/events?thread_role=ask_planning')
  })

  it('ignores stale sendMessage results after navigating to another node', async () => {
    const initialSession = makeSession()
    const sendDeferred = deferred<{
      user_message: {
        message_id: string
        role: 'user'
        content: string
        status: 'completed'
        error: null
        turn_id: string
        created_at: string
        updated_at: string
      }
      assistant_message: {
        message_id: string
        role: 'assistant'
        content: string
        status: 'pending'
        error: null
        turn_id: string
        created_at: string
        updated_at: string
      }
      active_turn_id: string
    }>()

    apiMock.getChatSession
      .mockResolvedValueOnce(initialSession)
      .mockResolvedValueOnce(makeSession({ created_at: 'session-2' }))
    apiMock.sendChatMessage.mockReturnValueOnce(sendDeferred.promise)

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    const sendPromise = useChatStore.getState().sendMessage('Hello from node 1')

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n2')
    })

    await act(async () => {
      sendDeferred.resolve({
        user_message: {
          message_id: 'msg-1',
          role: 'user',
          content: 'Hello from node 1',
          status: 'completed',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        assistant_message: {
          message_id: 'msg-2',
          role: 'assistant',
          content: '',
          status: 'pending',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        active_turn_id: 'turn-1',
      })
      await sendPromise
    })

    const state = useChatStore.getState()
    expect(state.activeNodeId).toBe('n2')
    expect(state.session?.created_at).toBe('session-2')
    expect(state.session?.messages).toEqual([])
    expect(state.isSending).toBe(false)
  })

  it('refetches session and reopens EventSource after SSE errors', async () => {
    vi.useFakeTimers()
    apiMock.getChatSession
      .mockResolvedValueOnce(makeSession({ created_at: 'initial-session' }))
      .mockResolvedValueOnce(makeSession({ created_at: 'recovered-session' }))

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    expect(MockEventSource.instances).toHaveLength(1)

    await act(async () => {
      MockEventSource.instances[0]?.onerror?.()
      await Promise.resolve()
    })

    expect(useChatStore.getState().session?.created_at).toBe('recovered-session')
    expect(MockEventSource.instances).toHaveLength(1)

    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.closedCount).toBeGreaterThanOrEqual(1)
  })

  it('disconnect closes EventSource and cancels pending reconnect', async () => {
    vi.useFakeTimers()
    apiMock.getChatSession
      .mockResolvedValueOnce(makeSession({ created_at: 'initial-session' }))
      .mockResolvedValueOnce(makeSession({ created_at: 'recovered-session' }))

    await act(async () => {
      await useChatStore.getState().loadSession('p1', 'n1')
    })

    await act(async () => {
      MockEventSource.instances[0]?.onerror?.()
      await Promise.resolve()
    })

    const instanceCountBeforeDisconnect = MockEventSource.instances.length

    act(() => {
      useChatStore.getState().disconnect()
    })

    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(instanceCountBeforeDisconnect)
    expect(useChatStore.getState().session).toBeNull()
  })
})

describe('applyChatEvent', () => {
  it('message_created dedups canonical messages already added from POST response', () => {
    const userMsg = {
      message_id: 'msg-1',
      role: 'user' as const,
      content: 'Hello',
      status: 'completed' as const,
      error: null,
      turn_id: 'turn-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const assistantMsg = {
      message_id: 'msg-2',
      role: 'assistant' as const,
      content: '',
      status: 'pending' as const,
      error: null,
      turn_id: 'turn-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const session = makeSession({
      messages: [userMsg, assistantMsg],
    })

    const result = applyChatEvent(session, {
      type: 'message_created',
      user_message: userMsg,
      assistant_message: assistantMsg,
      active_turn_id: 'turn-1',
    })

    expect(result.messages).toHaveLength(2)
    expect(result.active_turn_id).toBe('turn-1')
  })

  it('assistant_delta updates content and status', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-1',
          role: 'user',
          content: 'Hello',
          status: 'completed',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: '',
          status: 'pending',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const result = applyChatEvent(session, {
      type: 'assistant_delta',
      message_id: 'msg-2',
      delta: 'Hello ',
    })

    expect(result.messages[1].content).toBe('Hello ')
    expect(result.messages[1].status).toBe('streaming')
  })

  it('assistant_completed finalizes message', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: 'partial',
          status: 'streaming',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const result = applyChatEvent(session, {
      type: 'assistant_completed',
      message_id: 'msg-2',
      content: 'full response',
      thread_id: 'thread-1',
    })

    expect(result.messages[0].content).toBe('full response')
    expect(result.messages[0].status).toBe('completed')
    expect(result.active_turn_id).toBeNull()
    expect(result.thread_id).toBe('thread-1')
  })

  it('assistant_error sets error on message', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: '',
          status: 'pending',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const result = applyChatEvent(session, {
      type: 'assistant_error',
      message_id: 'msg-2',
      error: 'Something went wrong',
    })

    expect(result.messages[0].status).toBe('error')
    expect(result.messages[0].error).toBe('Something went wrong')
    expect(result.active_turn_id).toBeNull()
  })

  it('assistant_delta builds parts incrementally', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: '',
          status: 'pending',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const after1 = applyChatEvent(session, {
      type: 'assistant_delta',
      message_id: 'msg-2',
      delta: 'Hello ',
    })
    expect(after1.messages[0].parts).toHaveLength(1)
    expect(after1.messages[0].parts![0]).toEqual({
      type: 'assistant_text',
      content: 'Hello ',
      is_streaming: true,
    })

    const after2 = applyChatEvent(after1, {
      type: 'assistant_delta',
      message_id: 'msg-2',
      delta: 'world',
    })
    expect(after2.messages[0].parts).toHaveLength(1)
    expect(after2.messages[0].parts![0]).toEqual({
      type: 'assistant_text',
      content: 'Hello world',
      is_streaming: true,
    })
  })

  it('assistant_tool_call closes text part and adds tool', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: 'thinking',
          parts: [{ type: 'assistant_text' as const, content: 'thinking', is_streaming: true }],
          status: 'streaming',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const result = applyChatEvent(session, {
      type: 'assistant_tool_call',
      message_id: 'msg-2',
      tool_name: 'read_file',
      arguments: { path: '/test.py' },
      part_index: 1,
    })

    expect(result.messages[0].parts).toHaveLength(2)
    expect(result.messages[0].parts![0]).toEqual({
      type: 'assistant_text',
      content: 'thinking',
      is_streaming: false,
    })
    expect(result.messages[0].parts![1]).toMatchObject({
      type: 'tool_call',
      tool_name: 'read_file',
      status: 'running',
    })
  })

  it('assistant_status adds or updates status pill', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: '',
          status: 'streaming',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const after1 = applyChatEvent(session, {
      type: 'assistant_status',
      message_id: 'msg-2',
      status_type: 'running',
      label: 'Working...',
    })
    expect(after1.messages[0].parts).toHaveLength(1)
    expect(after1.messages[0].parts![0]).toMatchObject({
      type: 'status_block',
      status_type: 'running',
      label: 'Working...',
    })

    // Second status updates the existing one
    const after2 = applyChatEvent(after1, {
      type: 'assistant_status',
      message_id: 'msg-2',
      status_type: 'idle',
      label: 'Idle',
    })
    expect(after2.messages[0].parts).toHaveLength(1)
    expect(after2.messages[0].parts![0]).toMatchObject({
      type: 'status_block',
      status_type: 'idle',
    })
  })

  it('assistant_completed removes status blocks and completes tools', () => {
    const session = makeSession({
      active_turn_id: 'turn-1',
      messages: [
        {
          message_id: 'msg-2',
          role: 'assistant',
          content: 'partial',
          parts: [
            { type: 'assistant_text' as const, content: 'partial', is_streaming: true },
            { type: 'tool_call' as const, tool_name: 'shell', arguments: {}, call_id: null, status: 'running' as const },
            { type: 'status_block' as const, status_type: 'running', label: 'Working...', timestamp: '2026-01-01T00:00:00Z' },
          ],
          status: 'streaming',
          error: null,
          turn_id: 'turn-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    })

    const result = applyChatEvent(session, {
      type: 'assistant_completed',
      message_id: 'msg-2',
      content: 'full response',
      thread_id: 'thread-1',
    })

    expect(result.messages[0].parts).toHaveLength(2)
    expect(result.messages[0].parts![0]).toMatchObject({
      type: 'assistant_text',
      is_streaming: false,
    })
    expect(result.messages[0].parts![1]).toMatchObject({
      type: 'tool_call',
      status: 'completed',
    })
  })
})
