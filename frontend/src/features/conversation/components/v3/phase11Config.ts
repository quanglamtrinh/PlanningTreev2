export type MessagesV3Phase11Mode = 'off' | 'shadow' | 'on'

export const PHASE11_MODE_ENV_FLAG = 'VITE_PTM_PHASE11_HEAVY_COMPUTE_MODE'
export const PHASE11_WORKER_DIFF_THRESHOLD_CHARS_ENV_FLAG = 'VITE_PTM_PHASE11_WORKER_DIFF_THRESHOLD_CHARS'
export const PHASE11_WORKER_TIMEOUT_MS_ENV_FLAG = 'VITE_PTM_PHASE11_WORKER_TIMEOUT_MS'

export const PHASE11_DEFAULT_DIFF_THRESHOLD_CHARS = 8 * 1024
export const PHASE11_DEFAULT_WORKER_TIMEOUT_MS = 300
export const PHASE11_DEFAULT_DEFERRED_TIMEOUT_MS = 800

function parsePositiveInteger(
  value: unknown,
  fallback: number,
): number {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.floor(value)
  }
  const parsed = Number.parseInt(String(value ?? '').trim(), 10)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return parsed
}

export function normalizeMessagesV3Phase11Mode(
  value: string | null | undefined,
): MessagesV3Phase11Mode {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'shadow') {
    return 'shadow'
  }
  if (normalized === 'on') {
    return 'on'
  }
  return 'off'
}

export function resolveMessagesV3Phase11Mode(
  modeOverride: MessagesV3Phase11Mode | null | undefined,
): MessagesV3Phase11Mode {
  if (modeOverride) {
    return normalizeMessagesV3Phase11Mode(modeOverride)
  }
  const env = import.meta.env as Record<string, unknown>
  return normalizeMessagesV3Phase11Mode(String(env[PHASE11_MODE_ENV_FLAG] ?? 'off'))
}

export function resolvePhase11WorkerDiffThresholdCharsFromEnv(): number {
  const env = import.meta.env as Record<string, unknown>
  return parsePositiveInteger(
    env[PHASE11_WORKER_DIFF_THRESHOLD_CHARS_ENV_FLAG],
    PHASE11_DEFAULT_DIFF_THRESHOLD_CHARS,
  )
}

export function resolvePhase11WorkerTimeoutMsFromEnv(
  mode: 'interactive' | 'deferred',
): number {
  const env = import.meta.env as Record<string, unknown>
  const configured = parsePositiveInteger(
    env[PHASE11_WORKER_TIMEOUT_MS_ENV_FLAG],
    PHASE11_DEFAULT_WORKER_TIMEOUT_MS,
  )
  if (mode === 'deferred') {
    return Math.max(configured, PHASE11_DEFAULT_DEFERRED_TIMEOUT_MS)
  }
  return configured
}
