import { describe, expect, it } from 'vitest'

import {
  computeTrailingCommandOutput,
  computeTrailingCommandOutputIncremental,
  type CommandOutputTailCache,
} from '../../src/features/conversation/components/v3/commandOutputTail'

describe('commandOutputTail', () => {
  it('matches baseline trailing output behavior', () => {
    const output = ['l1', 'l2', 'l3', 'l4', 'l5'].join('\n')
    expect(computeTrailingCommandOutput(output, 3)).toBe('l3\nl4\nl5')
  })

  it('uses incremental append path for append-only updates', () => {
    const initial = computeTrailingCommandOutputIncremental({
      previous: null,
      itemKey: 'item-1',
      outputText: 'a\nb',
      maxLines: 4,
    })
    const next = computeTrailingCommandOutputIncremental({
      previous: initial.cache,
      itemKey: 'item-1',
      outputText: 'a\nb\nc\nd',
      maxLines: 4,
    })

    expect(next.usedIncrementalAppend).toBe(true)
    expect(next.didRebuild).toBe(false)
    expect(next.visibleOutput).toBe('a\nb\nc\nd')
  })

  it('rebuilds cache when output mutates non-append', () => {
    const initial = computeTrailingCommandOutputIncremental({
      previous: null,
      itemKey: 'item-1',
      outputText: 'line-1\nline-2',
      maxLines: 10,
    })
    const next = computeTrailingCommandOutputIncremental({
      previous: initial.cache as CommandOutputTailCache,
      itemKey: 'item-1',
      outputText: 'line-1-updated\nline-2',
      maxLines: 10,
    })

    expect(next.usedIncrementalAppend).toBe(false)
    expect(next.didRebuild).toBe(true)
    expect(next.visibleOutput).toBe('line-1-updated\nline-2')
  })

  it('respects max line trailing window in incremental mode', () => {
    let state: CommandOutputTailCache | null = null
    const updates = ['1', '1\n2', '1\n2\n3', '1\n2\n3\n4', '1\n2\n3\n4\n5']
    let lastVisible = ''

    for (const outputText of updates) {
      const result = computeTrailingCommandOutputIncremental({
        previous: state,
        itemKey: 'item-1',
        outputText,
        maxLines: 3,
      })
      state = result.cache
      lastVisible = result.visibleOutput
    }

    expect(lastVisible).toBe('3\n4\n5')
  })
})
