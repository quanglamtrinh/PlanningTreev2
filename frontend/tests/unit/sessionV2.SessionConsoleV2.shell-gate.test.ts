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

describe('SessionConsoleV2 shell-only guard', () => {
  it('consumes useSessionFacadeV2 and avoids direct runtime API imports', () => {
    const source = readFrontendSource('features/session_v2/shell/SessionConsoleV2.tsx')

    expect(source).toContain('useSessionFacadeV2')
    expect(source).toContain('const { state, commands } = useSessionFacadeV2()')
    expect(source).toContain('visibleRows={state.activeVisibleTranscriptRows}')

    expect(source).not.toContain('startThreadV2')
    expect(source).not.toContain('resumeThreadV2')
    expect(source).not.toContain('startTurnV2')
    expect(source).not.toContain('interruptTurnV2')
    expect(source).not.toContain('listPendingRequestsV2')
    expect(source).not.toContain('openThreadEventsStreamV2')
  })
})
