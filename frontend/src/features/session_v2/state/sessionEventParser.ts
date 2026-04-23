import type { SessionEventEnvelope } from '../contracts'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function parseSessionEvent(raw: string): SessionEventEnvelope | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isRecord(parsed)) {
    return null
  }
  if (typeof parsed.method !== 'string' || typeof parsed.threadId !== 'string' || typeof parsed.eventSeq !== 'number') {
    return null
  }
  return parsed as unknown as SessionEventEnvelope
}
