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

const removedThreadStore = `useThreadByIdStore${'V3'}`
const removedMessages = `Messages${'V3'}`
const removedCodexStoreFile = `codex-${'store'}`

describe('BreadcrumbChatViewV2 shell gate', () => {
  it('uses Session V2 and Workflow V2 runtime paths in the controller', () => {
    const source = readFrontendSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')

    expect(source).toContain('useSessionFacadeV2')
    expect(source).toContain("pendingRequestScope: 'activeThread'")
    expect(source).toContain('useWorkflowStateV2')
    expect(source).toContain('useWorkflowEventBridgeV2')
    expect(source).toContain('buildWorkflowProjectionV2')
    expect(source).not.toContain('breadcrumbV3SessionUiAdapter')
    expect(source).not.toContain(removedThreadStore)
    expect(source).not.toContain(removedMessages)
    expect(source).not.toContain('useCodexStore')
    expect(source).not.toContain(removedCodexStoreFile)
    expect(source).not.toContain('getChatSession')
    expect(source).not.toContain('sendMessage')
    expect(source).not.toContain('useWorkflowStateStoreV3')
    expect(source).not.toContain('useWorkflowEventBridgeV3')
    expect(source).not.toContain('resolveWorkflowProjection')
    expect(source).not.toContain('selectFeedRenderState')
    expect(source).not.toContain('selectComposerState')
    expect(source).not.toContain('selectThreadActions')
    expect(source).not.toContain('selectTransportBannerState')
  })

  it('keeps the view component presentational', () => {
    const source = readFrontendSource('features/conversation/BreadcrumbChatViewV2.tsx')

    expect(source).toContain('BreadcrumbThreadPaneV2')
    expect(source).toContain('NodeDetailCard')
    expect(source).not.toContain('useSessionFacadeV2')
    expect(source).not.toContain('useWorkflowStateV2')
    expect(source).not.toContain('breadcrumbV3SessionUiAdapter')
    expect(source).not.toContain(removedThreadStore)
  })
})
