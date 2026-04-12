import type { ThreadEventV2, ThreadEventV3, ThreadRole, WorkflowEventV2 } from '../../../api/types'

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

export type ThreadStreamOpenEnvelopeV3 = {
  type: 'stream_open'
  projectId: string
  nodeId: string
  threadRole: ThreadRole
  threadId: string
  snapshotVersion: number | null
  occurredAt: string
  payload: Record<string, unknown>
}

export type ParsedThreadStreamFrameV3 =
  | {
      kind: 'business'
      event: ThreadEventV3
      legacyFallbackUsed: boolean
    }
  | {
      kind: 'stream_open'
      envelope: ThreadStreamOpenEnvelopeV3
      legacyFallbackUsed: boolean
    }

const BUSINESS_EVENT_TYPES = new Set<ThreadEventV3['type']>([
  'thread.snapshot.v3',
  'conversation.item.upsert.v3',
  'conversation.item.patch.v3',
  'thread.lifecycle.v3',
  'conversation.ui.plan_ready.v3',
  'conversation.ui.user_input.v3',
  'thread.error.v3',
])

function asOptionalString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const cleaned = value.trim()
  return cleaned.length > 0 ? cleaned : null
}

function asOptionalThreadRole(value: unknown): ThreadRole | null {
  const candidate = asOptionalString(value)
  if (candidate === 'execution' || candidate === 'ask_planning' || candidate === 'audit') {
    return candidate
  }
  return null
}

function asOptionalPayload(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asOptionalSnapshotVersion(value: unknown): number | null {
  if (value === null) {
    return null
  }
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    return null
  }
  return value
}

function asOptionalOccurredAtMs(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0) {
    return null
  }
  return value
}

function toIsoFromMs(ms: number): string {
  return new Date(ms).toISOString()
}

function toOccurredAtMs(isoTime: string): number {
  const parsed = Date.parse(isoTime)
  if (Number.isNaN(parsed) || parsed < 0) {
    throw new Error(`Invalid occurredAt value: ${isoTime}`)
  }
  return parsed
}

function ensureNoLegacyCanonicalMismatch(
  legacyValue: string | number | null,
  canonicalValue: string | number | null,
  fieldName: string,
): void {
  if (legacyValue == null || canonicalValue == null) {
    return
  }
  if (legacyValue !== canonicalValue) {
    throw new Error(`Envelope ${fieldName} mismatch between canonical and legacy aliases.`)
  }
}

export function parseThreadEventEnvelopeV3(data: string): ParsedThreadStreamFrameV3 {
  const parsed = ensureParsedRecord(data)
  if (
    parsed.channel !== 'thread' ||
    (typeof parsed.type !== 'string' && typeof parsed.event_type !== 'string')
  ) {
    throw new Error('Expected a thread event envelope.')
  }

  const payload = asOptionalPayload(parsed.payload)
  if (!payload) {
    throw new Error('Thread envelope payload must be an object.')
  }

  const projectId = asOptionalString(parsed.projectId)
  const nodeId = asOptionalString(parsed.nodeId)
  const threadRole =
    asOptionalThreadRole(parsed.threadRole) ??
    asOptionalThreadRole((payload.snapshot as Record<string, unknown> | undefined)?.threadRole)
  if (!projectId || !nodeId || !threadRole) {
    throw new Error('Thread envelope missing required context fields (projectId/nodeId/threadRole).')
  }

  const canonicalEventType = asOptionalString(parsed.event_type)
  const legacyEventType = asOptionalString(parsed.type)
  ensureNoLegacyCanonicalMismatch(legacyEventType, canonicalEventType, 'event_type')
  const eventType = canonicalEventType ?? legacyEventType
  if (!eventType) {
    throw new Error('Thread envelope missing event type.')
  }

  const canonicalSnapshotVersion = asOptionalSnapshotVersion(parsed.snapshot_version)
  const legacySnapshotVersion = asOptionalSnapshotVersion(parsed.snapshotVersion)
  ensureNoLegacyCanonicalMismatch(legacySnapshotVersion, canonicalSnapshotVersion, 'snapshot_version')
  const snapshotVersion = canonicalSnapshotVersion ?? legacySnapshotVersion

  const canonicalOccurredAtMs = asOptionalOccurredAtMs(parsed.occurred_at_ms)
  const legacyOccurredAt = asOptionalString(parsed.occurredAt)
  if (legacyOccurredAt && canonicalOccurredAtMs != null) {
    ensureNoLegacyCanonicalMismatch(toOccurredAtMs(legacyOccurredAt), canonicalOccurredAtMs, 'occurred_at')
  }
  const occurredAt =
    legacyOccurredAt ?? (canonicalOccurredAtMs != null ? toIsoFromMs(canonicalOccurredAtMs) : null)
  if (!occurredAt) {
    throw new Error('Thread envelope missing occurredAt/occurred_at_ms.')
  }

  if (eventType === 'stream_open') {
    const canonicalThreadId = asOptionalString(parsed.thread_id)
    const legacyThreadId = asOptionalString((payload.threadId as unknown) ?? parsed.threadId)
    ensureNoLegacyCanonicalMismatch(legacyThreadId, canonicalThreadId, 'thread_id')
    const threadId = canonicalThreadId ?? legacyThreadId
    if (!threadId) {
      throw new Error('stream_open envelope missing thread_id/threadId.')
    }
    return {
      kind: 'stream_open',
      envelope: {
        type: 'stream_open',
        projectId,
        nodeId,
        threadRole,
        threadId,
        snapshotVersion,
        occurredAt,
        payload,
      },
      legacyFallbackUsed: canonicalEventType == null || canonicalThreadId == null || canonicalOccurredAtMs == null,
    }
  }

  const canonicalEventId = asOptionalString(parsed.event_id)
  const legacyEventId = asOptionalString(parsed.eventId)
  ensureNoLegacyCanonicalMismatch(legacyEventId, canonicalEventId, 'event_id')
  const eventId = canonicalEventId ?? legacyEventId
  if (!eventId) {
    throw new Error('Business event envelope missing event_id/eventId.')
  }
  if (!/^\d+$/.test(eventId)) {
    throw new Error(`Invalid event_id format: ${eventId}`)
  }

  const canonicalThreadId = asOptionalString(parsed.thread_id)
  const payloadSnapshot = asOptionalPayload(payload.snapshot)
  const payloadItem = asOptionalPayload(payload.item)
  const legacyThreadId =
    asOptionalString(parsed.threadId) ??
    asOptionalString(payloadSnapshot?.threadId) ??
    asOptionalString(payloadItem?.threadId)
  ensureNoLegacyCanonicalMismatch(legacyThreadId, canonicalThreadId, 'thread_id')
  const threadId = canonicalThreadId ?? legacyThreadId
  if (!threadId) {
    throw new Error('Business event envelope missing thread_id/threadId.')
  }

  if (!BUSINESS_EVENT_TYPES.has(eventType as ThreadEventV3['type'])) {
    throw new Error(`Unsupported thread business event type: ${eventType}`)
  }

  if (snapshotVersion == null) {
    throw new Error('Business event envelope missing snapshot_version/snapshotVersion.')
  }

  const hasCanonicalBusinessEnvelope =
    canonicalEventId != null &&
    canonicalEventType != null &&
    canonicalThreadId != null &&
    canonicalSnapshotVersion != null &&
    canonicalOccurredAtMs != null
  const hasLegacyBusinessEnvelope =
    legacyEventId != null &&
    legacyEventType != null &&
    legacySnapshotVersion != null &&
    legacyOccurredAt != null
  if (!hasCanonicalBusinessEnvelope && !hasLegacyBusinessEnvelope) {
    throw new Error('Business event envelope missing both canonical and legacy required fields.')
  }

  const event = {
    eventId,
    channel: 'thread',
    projectId,
    nodeId,
    threadRole,
    occurredAt,
    snapshotVersion,
    type: eventType as ThreadEventV3['type'],
    payload: payload as ThreadEventV3['payload'],
  } as ThreadEventV3

  return {
    kind: 'business',
    event,
    legacyFallbackUsed: !hasCanonicalBusinessEnvelope,
  }
}

export function parseWorkflowEventEnvelope(data: string): WorkflowEventV2 {
  const parsed = ensureParsedRecord(data)
  if (parsed.channel !== 'workflow' || typeof parsed.type !== 'string') {
    throw new Error('Expected a workflow event envelope.')
  }
  return parsed as unknown as WorkflowEventV2
}
