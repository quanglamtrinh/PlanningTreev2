import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { McpElicitationOverlay } from '../../src/features/session_v2/components/McpElicitationOverlay'
import type { PendingServerRequest } from '../../src/features/session_v2/contracts'

function request(payload: Record<string, unknown>): PendingServerRequest {
  return {
    requestId: 'req-1',
    rawRequestId: 'raw-1',
    method: 'mcpServer/elicitation/request',
    threadId: 'thread-1',
    turnId: 'turn-1',
    itemId: null,
    status: 'pending',
    occurredAtMs: 1,
    params: payload,
    payload,
  }
}

describe('McpElicitationOverlay', () => {
  it('renders richer schema fields and resolves accept action', async () => {
    const onResolve = vi.fn(async () => undefined)
    const onReject = vi.fn(async () => undefined)

    render(
      <McpElicitationOverlay
        request={request({
          title: 'Authorize MCP',
          message: 'Choose access',
          requestedSchema: {
            type: 'object',
            required: ['scope', 'confirm'],
            properties: {
              scope: { title: 'Scope', type: 'string', enum: ['read', 'write'] },
              confirm: { title: 'Confirm', type: 'boolean' },
              count: { title: 'Count', type: 'integer' },
            },
          },
        })}
        onResolve={onResolve}
        onReject={onReject}
      />,
    )

    fireEvent.change(screen.getByLabelText(/Scope/), { target: { value: 'read' } })
    fireEvent.change(screen.getByLabelText(/Confirm/), { target: { value: 'true' } })
    fireEvent.change(screen.getByLabelText(/Count/), { target: { value: '3' } })
    fireEvent.click(screen.getByText('Submit'))

    await waitFor(() => expect(onResolve).toHaveBeenCalled())
    expect(onResolve).toHaveBeenCalledWith('req-1', {
      action: 'accept',
      response: { scope: 'read', confirm: true, count: 3 },
    })
    expect(onReject).not.toHaveBeenCalled()
  })
})
