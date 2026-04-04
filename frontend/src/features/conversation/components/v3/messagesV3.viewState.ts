const VIEW_STATE_SCHEMA_VERSION = 1
const VIEW_STATE_MAX_BYTES = 16 * 1024

export type MessagesV3ViewState = {
  schemaVersion: number
  expandedItemIds: string[]
  collapsedToolGroupIds: string[]
  dismissedPlanReadyKeys: string[]
  updatedAt: string
}

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function normalizeStringList(value: unknown, maxSize: number): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  const next: string[] = []
  const seen = new Set<string>()
  for (const raw of value) {
    const normalized = String(raw ?? '').trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    next.push(normalized)
    if (next.length >= maxSize) {
      break
    }
  }
  return next
}

function toDefaultState(): MessagesV3ViewState {
  return {
    schemaVersion: VIEW_STATE_SCHEMA_VERSION,
    expandedItemIds: [],
    collapsedToolGroupIds: [],
    dismissedPlanReadyKeys: [],
    updatedAt: new Date().toISOString(),
  }
}

function toStorageKey(threadId: string): string {
  return `ptm.uiux.v3.thread.${threadId}.viewState`
}

function encodeByteLength(text: string): number {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(text).length
  }
  return text.length
}

function clampToSize(state: MessagesV3ViewState): MessagesV3ViewState {
  const next: MessagesV3ViewState = {
    ...state,
    expandedItemIds: [...state.expandedItemIds],
    collapsedToolGroupIds: [...state.collapsedToolGroupIds],
    dismissedPlanReadyKeys: [...state.dismissedPlanReadyKeys],
  }
  let serialized = JSON.stringify(next)
  if (encodeByteLength(serialized) <= VIEW_STATE_MAX_BYTES) {
    return next
  }

  while (next.dismissedPlanReadyKeys.length > 0 && encodeByteLength(serialized) > VIEW_STATE_MAX_BYTES) {
    next.dismissedPlanReadyKeys.shift()
    serialized = JSON.stringify(next)
  }
  while (next.expandedItemIds.length > 0 && encodeByteLength(serialized) > VIEW_STATE_MAX_BYTES) {
    next.expandedItemIds.shift()
    serialized = JSON.stringify(next)
  }
  while (next.collapsedToolGroupIds.length > 0 && encodeByteLength(serialized) > VIEW_STATE_MAX_BYTES) {
    next.collapsedToolGroupIds.shift()
    serialized = JSON.stringify(next)
  }
  return next
}

export function loadMessagesV3ViewState(threadId: string): MessagesV3ViewState {
  const normalizedThreadId = String(threadId ?? '').trim()
  if (!normalizedThreadId || !canUseStorage()) {
    return toDefaultState()
  }
  try {
    const raw = window.localStorage.getItem(toStorageKey(normalizedThreadId))
    if (!raw) {
      return toDefaultState()
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (Number(parsed.schemaVersion) !== VIEW_STATE_SCHEMA_VERSION) {
      return toDefaultState()
    }
    return clampToSize({
      schemaVersion: VIEW_STATE_SCHEMA_VERSION,
      expandedItemIds: normalizeStringList(parsed.expandedItemIds, 1000),
      collapsedToolGroupIds: normalizeStringList(parsed.collapsedToolGroupIds, 1000),
      dismissedPlanReadyKeys: normalizeStringList(parsed.dismissedPlanReadyKeys, 2000),
      updatedAt: String(parsed.updatedAt ?? new Date().toISOString()),
    })
  } catch {
    return toDefaultState()
  }
}

export function saveMessagesV3ViewState(threadId: string, state: MessagesV3ViewState): void {
  const normalizedThreadId = String(threadId ?? '').trim()
  if (!normalizedThreadId || !canUseStorage()) {
    return
  }
  const normalized: MessagesV3ViewState = clampToSize({
    schemaVersion: VIEW_STATE_SCHEMA_VERSION,
    expandedItemIds: normalizeStringList(state.expandedItemIds, 1000),
    collapsedToolGroupIds: normalizeStringList(state.collapsedToolGroupIds, 1000),
    dismissedPlanReadyKeys: normalizeStringList(state.dismissedPlanReadyKeys, 2000),
    updatedAt: String(state.updatedAt || new Date().toISOString()),
  })
  try {
    window.localStorage.setItem(toStorageKey(normalizedThreadId), JSON.stringify(normalized))
  } catch {
    // Best-effort persistence only.
  }
}
