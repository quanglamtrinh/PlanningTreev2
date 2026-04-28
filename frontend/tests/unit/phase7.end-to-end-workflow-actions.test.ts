import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readSource(relativePath: string): string {
  const direct = resolve(process.cwd(), 'src', relativePath)
  try {
    return readFileSync(direct, 'utf-8')
  } catch {
    return readFileSync(resolve(process.cwd(), 'frontend', 'src', relativePath), 'utf-8')
  }
}

describe('phase 7 end-to-end workflow action guardrails', () => {
  it('keeps Breadcrumb V2 on Workflow V2 action commands', () => {
    const controller = readSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')

    expect(controller).toContain('ensureThread')
    expect(controller).not.toContain('startPackageReview')
    expect(controller).toContain("'ask_planning'")
    expect(controller).not.toContain("'start_package_review'")
    expect(controller).not.toContain('useWorkflowStateStoreV3')
    expect(controller).not.toContain('useWorkflowEventBridgeV3')
  })

  it('keeps package review in Workflow V2 modules but out of Breadcrumb projection', () => {
    const client = readSource('features/workflow_v2/api/client.ts')
    const store = readSource('features/workflow_v2/store/workflowStateStoreV2.ts')
    const projection = readSource('features/conversation/workflowThreadLaneV2.ts')

    expect(client).toContain('startPackageReviewV2')
    expect(client).toContain('/package-review/start')
    expect(store).toContain('startPackageReview')
    expect(projection).not.toContain('workflow-start-package-review')
    expect(projection).not.toContain('workflow-ensure-ask-thread')
  })
})
