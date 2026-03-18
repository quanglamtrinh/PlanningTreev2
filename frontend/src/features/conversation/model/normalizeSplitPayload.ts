export type SplitPayloadMeta = {
  label: string
  value: string
}

export type NormalizedSplitSubtaskCard = {
  key: string
  title: string
  body: string | null
  meta: SplitPayloadMeta[]
}

export const UNSUPPORTED_SPLIT_PAYLOAD_MESSAGE =
  "This historical split result uses a legacy format and can't be rendered in the current UI."

export type NormalizedSplitPayload =
  | {
      kind: 'subtasks'
      cards: NormalizedSplitSubtaskCard[]
    }
  | {
      kind: 'unsupported'
      message: string
    }

export function normalizeSplitPayload(payload: Record<string, unknown> | null): NormalizedSplitPayload | null {
  if (!payload) {
    return null
  }

  const materializedFamily = asString(payload.family)
  const materializedSubtasks = Array.isArray(payload.subtasks) ? payload.subtasks : null
  if (materializedFamily === 'flat_subtasks_v1' && materializedSubtasks) {
    const cards = materializedSubtasks
      .map((subtask, index) => normalizeMaterializedSubtaskCard(subtask, index))
      .filter((card): card is NormalizedSplitSubtaskCard => card !== null)
    if (cards.length === materializedSubtasks.length && cards.length > 0) {
      return {
        kind: 'subtasks',
        cards,
      }
    }
    return {
      kind: 'unsupported',
      message: UNSUPPORTED_SPLIT_PAYLOAD_MESSAGE,
    }
  }

  const subtasks = Array.isArray(payload.subtasks) ? payload.subtasks : null
  if (!subtasks) {
    return {
      kind: 'unsupported',
      message: UNSUPPORTED_SPLIT_PAYLOAD_MESSAGE,
    }
  }

  const cards = subtasks
    .map((subtask, index) => normalizeCanonicalSubtaskCard(subtask, index))
    .filter((card): card is NormalizedSplitSubtaskCard => card !== null)
  if (cards.length !== subtasks.length || cards.length === 0) {
    return {
      kind: 'unsupported',
      message: UNSUPPORTED_SPLIT_PAYLOAD_MESSAGE,
    }
  }

  return {
    kind: 'subtasks',
    cards,
  }
}

function normalizeCanonicalSubtaskCard(subtask: unknown, index: number): NormalizedSplitSubtaskCard | null {
  const typedSubtask = asRecord(subtask)
  if (!typedSubtask) {
    return null
  }

  const id = asString(typedSubtask.id)
  const title = asString(typedSubtask.title)
  const objective = asString(typedSubtask.objective)
  const whyNow = asString(typedSubtask.why_now)
  if (id || title || objective || whyNow) {
    return {
      key: `${id ?? `S${index + 1}`}-${title ?? 'subtask'}`,
      title: [id, title].filter(Boolean).join(' / ') || `Subtask ${index + 1}`,
      body: objective,
      meta: whyNow ? [{ label: 'Why now', value: whyNow }] : [],
    }
  }

  return null
}

function normalizeMaterializedSubtaskCard(subtask: unknown, index: number): NormalizedSplitSubtaskCard | null {
  const typedSubtask = asRecord(subtask)
  if (!typedSubtask) {
    return null
  }
  const id = asString(typedSubtask.subtask_id)
  const title = asString(typedSubtask.title)
  const objective = asString(typedSubtask.objective)
  const whyNow = asString(typedSubtask.why_now)
  if (!id || !title || !objective || !whyNow) {
    return null
  }
  return {
    key: `${id}-${title}`,
    title: [id, title].join(' / ') || `Subtask ${index + 1}`,
    body: objective,
    meta: [{ label: 'Why now', value: whyNow }],
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}
