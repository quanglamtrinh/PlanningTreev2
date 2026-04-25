type SessionDebugWindow = Window & {
  __PT_DEBUG_SESSION_V2__?: boolean
  __PT_SESSION_V2_LOGS__?: Array<{
    ts: string
    scope: string
    message: string
    details?: Record<string, unknown>
  }>
}

function isDebugEnabled(): boolean {
  if (typeof window !== 'undefined') {
    const flag = (window as SessionDebugWindow).__PT_DEBUG_SESSION_V2__
    if (flag === true) {
      return true
    }
    if (flag === false) {
      return false
    }
  }
  return Boolean(import.meta.env.DEV)
}

export function logSessionDebug(scope: string, message: string, details?: Record<string, unknown>): void {
  if (!isDebugEnabled()) {
    return
  }
  const ts = new Date().toISOString()
  if (typeof window !== 'undefined') {
    const target = (window as SessionDebugWindow)
    const logs = target.__PT_SESSION_V2_LOGS__ ?? []
    logs.push({
      ts,
      scope,
      message,
      details,
    })
    if (logs.length > 500) {
      logs.shift()
    }
    target.__PT_SESSION_V2_LOGS__ = logs
  }
  if (details) {
    console.info(`[session_v2:${scope}] ${message}`, { ts, ...details })
    return
  }
  console.info(`[session_v2:${scope}] ${message}`, { ts })
}
