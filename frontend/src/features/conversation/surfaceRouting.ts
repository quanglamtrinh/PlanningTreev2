export type ThreadTab = 'root' | 'ask' | 'execution' | 'audit'
export type WorkflowThreadTab = Exclude<ThreadTab, 'root'>

export function parseThreadTab(rawValue: string | null): ThreadTab | null {
  if (rawValue === 'review') {
    return 'audit'
  }
  if (rawValue === 'root' || rawValue === 'ask' || rawValue === 'execution' || rawValue === 'audit') {
    return rawValue
  }
  return null
}

export function buildChatV2Url(
  projectId: string,
  nodeId: string,
  threadTab: ThreadTab,
): string {
  return `/projects/${projectId}/nodes/${nodeId}/chat-v2?thread=${threadTab}`
}

export function resolveV2RouteTarget(options: {
  requestedThreadTab: ThreadTab | null
  isReviewNode: boolean
  isRootNode?: boolean
}): { surface: 'legacy' | 'v2'; threadTab: ThreadTab } {
  const { requestedThreadTab, isReviewNode, isRootNode = false } = options

  if (isRootNode) {
    return { surface: 'v2', threadTab: 'root' }
  }

  if (isReviewNode) {
    if (requestedThreadTab === 'ask') {
      return { surface: 'v2', threadTab: 'ask' }
    }
    return { surface: 'v2', threadTab: 'audit' }
  }
  if (requestedThreadTab === 'ask') {
    return { surface: 'v2', threadTab: 'ask' }
  }
  if (requestedThreadTab === 'execution' || requestedThreadTab === 'audit') {
    return { surface: 'v2', threadTab: requestedThreadTab }
  }
  return { surface: 'v2', threadTab: 'execution' }
}
