import { describe, expect, it } from 'vitest'

import { parseThreadEventEnvelope, parseWorkflowEventEnvelope } from '../../src/features/conversation/state/threadEventRouter'

describe('threadEventRouter', () => {
  it('parses canonical thread event envelopes', () => {
    const event = parseThreadEventEnvelope(
      JSON.stringify({
        eventId: '20',
        channel: 'thread',
        type: 'thread/status/changed',
        threadId: 'thread-1',
        payload: {},
      }),
    )

    expect(event.threadId).toBe('thread-1')
    expect(event.eventId).toBe('20')
  })

  it('parses canonical workflow event envelopes', () => {
    const event = parseWorkflowEventEnvelope(
      JSON.stringify({
        eventId: '21',
        channel: 'workflow',
        type: 'workflow/state_changed',
        projectId: 'project-1',
        nodeId: 'node-1',
      }),
    )

    expect(event.channel).toBe('workflow')
    expect(event.type).toBe('workflow/state_changed')
  })
})
