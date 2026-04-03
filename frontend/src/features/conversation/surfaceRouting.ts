import type { BootstrapStatus } from '../../api/types'

export type ThreadTab = 'ask' | 'execution' | 'audit'

export function parseThreadTab(rawValue: string | null): ThreadTab | null {
  if (rawValue === 'ask' || rawValue === 'execution' || rawValue === 'audit') {
    return rawValue
  }
  return null
}

export function buildLegacyChatUrl(
  projectId: string,
  nodeId: string,
  threadTab: ThreadTab = 'ask',
): string {
  return `/projects/${projectId}/nodes/${nodeId}/chat?thread=${threadTab}`
}

export function buildChatV2Url(
  projectId: string,
  nodeId: string,
  threadTab: Exclude<ThreadTab, 'ask'>,
): string {
  return `/projects/${projectId}/nodes/${nodeId}/chat-v2?thread=${threadTab}`
}

export function isExecutionAuditV2SurfaceEnabled(bootstrap: BootstrapStatus | null | undefined): boolean {
  if (!bootstrap) {
    return true
  }
  return bootstrap.execution_audit_v2_enabled === true
}

function parseEnvBoolean(raw: string): boolean | null {
  const normalized = raw.trim().toLowerCase()
  if (!normalized) {
    return null
  }
  if (normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on') {
    return true
  }
  if (normalized === '0' || normalized === 'false' || normalized === 'no' || normalized === 'off') {
    return false
  }
  return null
}

function readSharedV3FrontendEnvOverride(): boolean | null {
  return parseEnvBoolean(String(import.meta.env.VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND ?? ''))
}

function readLaneV3FrontendEnvOverride(lane: 'execution' | 'audit'): boolean | null {
  const laneRaw =
    lane === 'execution'
      ? String(import.meta.env.VITE_EXECUTION_UIUX_V3_FRONTEND ?? '')
      : String(import.meta.env.VITE_AUDIT_UIUX_V3_FRONTEND ?? '')
  const laneValue = parseEnvBoolean(laneRaw)
  if (laneValue !== null) {
    return laneValue
  }
  return readSharedV3FrontendEnvOverride()
}

export function isExecutionAuditUiuxV3FrontendEnabled(
  bootstrap: BootstrapStatus | null | undefined,
): boolean {
  const envOverride = readSharedV3FrontendEnvOverride()
  if (envOverride !== null) {
    return envOverride
  }
  return bootstrap?.execution_audit_uiux_v3_frontend_enabled === true
}

export function isExecutionUiuxV3FrontendEnabled(
  bootstrap: BootstrapStatus | null | undefined,
): boolean {
  const envOverride = readLaneV3FrontendEnvOverride('execution')
  if (envOverride !== null) {
    return envOverride
  }
  if (bootstrap?.execution_uiux_v3_frontend_enabled != null) {
    return bootstrap.execution_uiux_v3_frontend_enabled === true
  }
  return isExecutionAuditUiuxV3FrontendEnabled(bootstrap)
}

export function isAuditUiuxV3FrontendEnabled(
  bootstrap: BootstrapStatus | null | undefined,
): boolean {
  const envOverride = readLaneV3FrontendEnvOverride('audit')
  if (envOverride !== null) {
    return envOverride
  }
  if (bootstrap?.audit_uiux_v3_frontend_enabled != null) {
    return bootstrap.audit_uiux_v3_frontend_enabled === true
  }
  return isExecutionAuditUiuxV3FrontendEnabled(bootstrap)
}

export function resolveLegacyRouteTarget(options: {
  requestedThreadTab: ThreadTab | null
  isReviewNode: boolean
  executionAuditV2Enabled: boolean
}): { surface: 'legacy' | 'v2'; threadTab: ThreadTab } {
  const { requestedThreadTab, isReviewNode } = options
  if (isReviewNode) {
    return { surface: 'legacy', threadTab: 'audit' }
  }
  if (requestedThreadTab === 'execution' || requestedThreadTab === 'audit') {
    return {
      surface: options.executionAuditV2Enabled ? 'v2' : 'legacy',
      threadTab: requestedThreadTab,
    }
  }
  return { surface: 'legacy', threadTab: 'ask' }
}

export function resolveV2RouteTarget(options: {
  requestedThreadTab: ThreadTab | null
  isReviewNode: boolean
  executionAuditV2Enabled: boolean
}): { surface: 'legacy' | 'v2'; threadTab: ThreadTab } {
  const { requestedThreadTab, isReviewNode, executionAuditV2Enabled } = options

  if (!executionAuditV2Enabled) {
    if (isReviewNode) {
      return { surface: 'legacy', threadTab: 'audit' }
    }
    return { surface: 'legacy', threadTab: requestedThreadTab ?? 'ask' }
  }

  if (isReviewNode) {
    return { surface: 'legacy', threadTab: 'audit' }
  }
  if (requestedThreadTab === 'ask') {
    return { surface: 'legacy', threadTab: 'ask' }
  }
  if (requestedThreadTab === 'execution' || requestedThreadTab === 'audit') {
    return { surface: 'v2', threadTab: requestedThreadTab }
  }
  return { surface: 'v2', threadTab: 'execution' }
}
