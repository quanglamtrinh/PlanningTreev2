import { beforeEach, describe, expect, it } from 'vitest'

import { useThreadSessionStore } from '../../src/features/session_v2/store/threadSessionStore'

describe('threadSessionStore', () => {
  beforeEach(() => {
    useThreadSessionStore.getState().clear()
  })

  it('seeds thread list and sets active thread', () => {
    const store = useThreadSessionStore.getState()
    store.setThreadList([
      {
        id: 'thread-1',
        name: 'Thread 1',
        modelProvider: 'openai',
        cwd: 'C:/repo',
        ephemeral: false,
        archived: false,
        status: { type: 'idle' },
        createdAt: 1,
        updatedAt: 1,
        turns: [],
      },
    ])
    store.setActiveThreadId('thread-1')

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.threadOrder).toEqual(['thread-1'])
    expect(snapshot.activeThreadId).toBe('thread-1')
    expect(snapshot.threadsById['thread-1']?.name).toBe('Thread 1')
  })

  it('tracks stream reconnect counters', () => {
    const store = useThreadSessionStore.getState()
    store.markStreamConnected('thread-1')
    store.markStreamReconnect('thread-1')
    store.markStreamReconnect('thread-1')
    store.markStreamDisconnected('thread-1')

    const snapshot = useThreadSessionStore.getState()
    expect(snapshot.streamState.connectedByThread['thread-1']).toBe(false)
    expect(snapshot.streamState.reconnectCountByThread['thread-1']).toBe(2)
  })
})

