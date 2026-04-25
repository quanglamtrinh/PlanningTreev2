import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readFrontendSource(relativePath: string): string {
  const direct = resolve(process.cwd(), 'src', relativePath)
  try {
    return readFileSync(direct, 'utf-8')
  } catch {
    const nested = resolve(process.cwd(), 'frontend', 'src', relativePath)
    return readFileSync(nested, 'utf-8')
  }
}

describe('phase 6 active-path Workflow V2 guardrails', () => {
  it('cuts chat-v2 active path over to Workflow V2 store + bridge', () => {
    const breadcrumbController = readFrontendSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')

    expect(breadcrumbController).toContain("useSessionFacadeV2")
    expect(breadcrumbController).toContain("useWorkflowStateV2")
    expect(breadcrumbController).toContain("useWorkflowEventBridgeV2")
    expect(breadcrumbController).toContain("buildWorkflowProjectionV2")
    expect(breadcrumbController).not.toContain("useWorkflowStateStoreV3")
    expect(breadcrumbController).not.toContain("useWorkflowEventBridgeV3")
    expect(breadcrumbController).not.toContain("resolveWorkflowProjection")
  })

  it('keeps NodeDocumentEditor finish-task flow on V3 workflow store', () => {
    const nodeEditor = readFrontendSource('features/node/NodeDocumentEditor.tsx')

    expect(nodeEditor).toContain("useWorkflowStateStoreV3")
    expect(nodeEditor).not.toContain("useWorkflowStateStoreV2")
    expect(nodeEditor).toContain("finishTaskWorkflowV3")
  })

  it('uses /v3 project workflow events in the active V3 bridge', () => {
    const eventBridgeV3 = readFrontendSource('features/conversation/state/workflowEventBridgeV3.ts')

    expect(eventBridgeV3).toContain("buildProjectEventsUrlV3")
    expect(eventBridgeV3).not.toContain("buildProjectEventsUrlV2")
  })
})
