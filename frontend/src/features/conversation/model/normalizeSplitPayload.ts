export type SplitPayloadMeta = {
  label: string
  value: string
}

export type NormalizedSplitEpicCard = {
  key: string
  title: string
  body: string | null
  items: Array<{
    key: string
    title: string
    body: string | null
  }>
}

export type NormalizedSplitSubtaskCard = {
  key: string
  title: string
  body: string | null
  meta: SplitPayloadMeta[]
}

export type NormalizedSplitPayload =
  | {
      kind: 'epics'
      cards: NormalizedSplitEpicCard[]
    }
  | {
      kind: 'subtasks'
      cards: NormalizedSplitSubtaskCard[]
    }

export function normalizeSplitPayload(payload: Record<string, unknown> | null): NormalizedSplitPayload | null {
  if (!payload) {
    return null
  }

  const epics = Array.isArray(payload.epics) ? payload.epics : null
  if (epics) {
    return {
      kind: 'epics',
      cards: epics
        .map((epic, index) => {
          const typedEpic = asRecord(epic)
          if (!typedEpic) {
            return null
          }
          const phases = Array.isArray(typedEpic.phases) ? typedEpic.phases : []
          return {
            key: `${asString(typedEpic.title) ?? 'epic'}-${index}`,
            title: asString(typedEpic.title) ?? `Epic ${index + 1}`,
            body: asString(typedEpic.prompt),
            items: phases
              .map((phase, phaseIndex) => {
                const typedPhase = asRecord(phase)
                if (!typedPhase) {
                  return null
                }
                return {
                  key: `${asString(typedEpic.title) ?? 'phase'}-${phaseIndex}`,
                  title: asString(typedPhase.prompt) ?? `Phase ${phaseIndex + 1}`,
                  body: asString(typedPhase.definition_of_done),
                }
              })
              .filter((item): item is NonNullable<typeof item> => item !== null),
          }
        })
        .filter((card): card is NonNullable<typeof card> => card !== null),
    }
  }

  const subtasks = Array.isArray(payload.subtasks) ? payload.subtasks : null
  if (!subtasks) {
    return null
  }

  return {
    kind: 'subtasks',
    cards: subtasks
      .map((subtask, index) => normalizeSubtaskCard(subtask, index))
      .filter((card): card is NormalizedSplitSubtaskCard => card !== null),
  }
}

function normalizeSubtaskCard(subtask: unknown, index: number): NormalizedSplitSubtaskCard | null {
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

  const order = asNumber(typedSubtask.order) ?? index + 1
  const prompt = asString(typedSubtask.prompt)
  const riskReason = asString(typedSubtask.risk_reason)
  const whatUnblocks = asString(typedSubtask.what_unblocks)
  if (!prompt && !riskReason && !whatUnblocks) {
    return null
  }

  return {
    key: `${order}-${prompt ?? 'subtask'}`,
    title: `Slice ${order}`,
    body: prompt,
    meta: [
      ...(riskReason ? [{ label: 'Risk', value: riskReason }] : []),
      ...(whatUnblocks ? [{ label: 'Unblocks', value: whatUnblocks }] : []),
    ],
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

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
