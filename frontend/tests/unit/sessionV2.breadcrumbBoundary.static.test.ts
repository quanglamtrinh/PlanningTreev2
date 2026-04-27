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

describe('Breadcrumb V2 thread boundary', () => {
  it('renders and submits transcript through Session V2 instead of legacy thread APIs', () => {
    const source = readFrontendSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')

    expect(source).toContain('useSessionFacadeV2')
    expect(source).toContain('sessionCommands.selectThread')
    expect(source).toContain('sessionCommands.submit')
    expect(source).not.toContain('buildThreadByIdBasePathV3')
    expect(source).not.toContain('buildThreadByIdPathV3')
    expect(source).not.toContain('buildThreadByIdEventsUrlV3')
    expect(source).not.toContain('/threads/by-id/')
    expect(source).not.toContain('/chat/session')
    expect(source).not.toContain('/chat/message')
  })

  it('keeps legacy V3/chat client helpers out of the Breadcrumb V2 controller', () => {
    const source = readFrontendSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')

    expect(source).not.toContain("from '../../api/client'")
    expect(source).not.toContain("from '../../../api/client'")
    expect(source).not.toContain('getThreadByIdV3')
    expect(source).not.toContain('openThreadEventsV3')
    expect(source).not.toContain('sendMessage')
    expect(source).not.toContain('getChatSession')
  })

  it('does not use provider recover for normal Breadcrumb V2 resync paths', () => {
    const breadcrumbSource = readFrontendSource('features/conversation/useBreadcrumbConversationControllerV2.tsx')
    const facadeSource = readFrontendSource('features/session_v2/facade/useSessionFacadeV2.ts')

    expect(breadcrumbSource).toContain('sessionCommands.resyncThreadTranscript(laneTid)')
    expect(breadcrumbSource).not.toContain('recoverFromProvider')
    expect(breadcrumbSource).not.toContain('shouldRecoverProviderOnResync')
    expect(breadcrumbSource).not.toContain('recoverThreadFromProvider')
    expect(facadeSource).not.toContain('recoverFromProvider')
    expect(facadeSource).not.toContain('recoverThreadFromProvider')
    expect(facadeSource).toContain('hydrateThreadState(normalized, { force: true })')
  })
})
