import type { ThreadEventV2 } from '../../../api/types'

type WorkflowEventEnvelope = Record<string, unknown> & { channel: 'workflow'; type: string }

function ensureParsedRecord(data: string): Record<string, unknown> {
  const parsed = JSON.parse(data) as unknown
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Expected an object event envelope.')
  }
  return parsed as Record<string, unknown>
}

export function parseThreadEventEnvelope(data: string): ThreadEventV2 {
  const parsed = ensureParsedRecord(data)
  if (parsed.channel !== 'thread' || typeof parsed.type !== 'string') {
    throw new Error('Expected a thread event envelope.')
  }
  return parsed as unknown as ThreadEventV2
}

export function parseWorkflowEventEnvelope(data: string): WorkflowEventEnvelope {
  const parsed = ensureParsedRecord(data)
  if (parsed.channel !== 'workflow' || typeof parsed.type !== 'string') {
    throw new Error('Expected a workflow event envelope.')
  }
  return parsed as WorkflowEventEnvelope
}
