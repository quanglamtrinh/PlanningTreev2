import type { BootstrapStatus } from '../../api/types'

export type ThreadTab = 'ask' | 'execution' | 'audit' | 'package'

export function parseThreadTab(rawValue: string | null): ThreadTab | null {
  if (rawValue === 'review') {
    return 'audit'
  }
  if (rawValue === 'package-review') {
    return 'package'
  }
  if (
    rawValue === 'ask' ||
    rawValue === 'execution' ||
    rawValue === 'audit' ||
    rawValue === 'package'
  ) {
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
  threadTab: ThreadTab,
): string {
  return `/projects/${projectId}/nodes/${nodeId}/chat-v2?thread=${threadTab}`
}

export function isExecutionAuditV2SurfaceEnabled(_bootstrap: BootstrapStatus | null | undefined): boolean {
  return true
}

export function isExecutionAuditUiuxV3FrontendEnabled(
  _bootstrap: BootstrapStatus | null | undefined,
): boolean {
  return true
}

export function isExecutionUiuxV3FrontendEnabled(
  _bootstrap: BootstrapStatus | null | undefined,
): boolean {
  return true
}

export function isAuditUiuxV3FrontendEnabled(
  _bootstrap: BootstrapStatus | null | undefined,
): boolean {
  return true
}

export function resolveLegacyRouteTarget(options: {
  requestedThreadTab: ThreadTab | null
  isReviewNode: boolean
}): { surface: 'legacy' | 'v2'; threadTab: ThreadTab } {
  const { requestedThreadTab, isReviewNode } = options
  if (isReviewNode) {
    if (requestedThreadTab === 'ask') {
      return { surface: 'v2', threadTab: 'ask' }
    }
    return { surface: 'v2', threadTab: 'audit' }
  }
  return { surface: 'v2', threadTab: 'ask' }
}

export function resolveV2RouteTarget(options: {
  requestedThreadTab: ThreadTab | null
  isReviewNode: boolean
}): { surface: 'legacy' | 'v2'; threadTab: ThreadTab } {
  const { requestedThreadTab, isReviewNode } = options

  if (isReviewNode) {
    if (requestedThreadTab === 'ask') {
      return { surface: 'v2', threadTab: 'ask' }
    }
    return { surface: 'v2', threadTab: 'audit' }
  }
  if (requestedThreadTab === 'ask') {
    return { surface: 'v2', threadTab: 'ask' }
  }
  if (
    requestedThreadTab === 'execution' ||
    requestedThreadTab === 'audit' ||
    requestedThreadTab === 'package'
  ) {
    return { surface: 'v2', threadTab: requestedThreadTab }
  }
  return { surface: 'v2', threadTab: 'execution' }
}
