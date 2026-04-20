import { describe, expectTypeOf, it } from 'vitest'

import type {
  PendingServerRequest,
  ServerRequestEnvelope,
  TurnSteerRequestV4,
} from '../../src/features/session_v2/contracts'

describe('session_v2 contract parity', () => {
  it('accepts nullable turnId for pending request and server request envelope', () => {
    const pending: PendingServerRequest = {
      requestId: 'req-1',
      method: 'mcpServer/elicitation/request',
      threadId: 'thread-1',
      turnId: null,
      itemId: 'item-1',
      status: 'pending',
      createdAtMs: 1,
      submittedAtMs: null,
      resolvedAtMs: null,
      payload: {},
    }
    const envelope: ServerRequestEnvelope = {
      schemaVersion: 1,
      requestId: 'req-1',
      method: 'mcpServer/elicitation/request',
      threadId: 'thread-1',
      turnId: null,
      itemId: null,
      status: 'pending',
      occurredAtMs: 1,
      params: {},
    }

    expectTypeOf(pending.turnId).toEqualTypeOf<string | null>()
    expectTypeOf(envelope.turnId).toEqualTypeOf<string | null>()
  })

  it('requires expectedTurnId on steer request', () => {
    const request: TurnSteerRequestV4 = {
      clientActionId: 'steer-1',
      expectedTurnId: 'turn-1',
      input: [{ type: 'text', text: 'continue' }],
    }
    expectTypeOf(request.expectedTurnId).toEqualTypeOf<string>()
  })

  it('rejects missing or nullable expectedTurnId', () => {
    // @ts-expect-error expectedTurnId must be required.
    const missing: TurnSteerRequestV4 = { clientActionId: 'steer-2', input: [] }
    void missing

    // @ts-expect-error expectedTurnId must be a non-null string.
    const nullable: TurnSteerRequestV4 = { clientActionId: 'steer-3', expectedTurnId: null, input: [] }
    void nullable
  })
})

