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

  it('cuts NodeDocumentEditor finish-task flow over to Workflow V2', () => {
    const nodeEditor = readFrontendSource('features/node/NodeDocumentEditor.tsx')

    expect(nodeEditor).toContain("useWorkflowStateV2")
    expect(nodeEditor).toContain("startExecution")
    expect(nodeEditor).not.toContain("useWorkflowStateStoreV3")
    expect(nodeEditor).not.toContain("finishTaskWorkflowV3")
  })

})
