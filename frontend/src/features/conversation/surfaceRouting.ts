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
  return bootstrap?.execution_audit_v2_enabled === true
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
