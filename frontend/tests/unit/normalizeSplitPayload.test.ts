import { describe, expect, it } from 'vitest'

import { normalizeSplitPayload } from '../../src/features/conversation/model/normalizeSplitPayload'

describe('normalizeSplitPayload', () => {
  it('keeps legacy walking-skeleton epic payloads readable on transition read paths', () => {
    const normalized = normalizeSplitPayload({
      epics: [
        {
          title: 'Foundation',
          prompt: 'Stand up the initial skeleton for the project.',
          phases: [
            {
              prompt: 'Wire storage',
              definition_of_done: 'Project state persists successfully.',
            },
            {
              prompt: 'Render graph',
              definition_of_done: 'The graph renders the root node and first edge.',
            },
          ],
        },
      ],
    })

    expect(normalized).toEqual({
      kind: 'epics',
      cards: [
        {
          key: 'Foundation-0',
          title: 'Foundation',
          body: 'Stand up the initial skeleton for the project.',
          items: [
            {
              key: 'Foundation-0',
              title: 'Wire storage',
              body: 'Project state persists successfully.',
            },
            {
              key: 'Foundation-1',
              title: 'Render graph',
              body: 'The graph renders the root node and first edge.',
            },
          ],
        },
      ],
    })
  })

  it('normalizes canonical flat subtasks for shared split rendering', () => {
    const normalized = normalizeSplitPayload({
      subtasks: [
        {
          id: 'S1',
          title: 'Setup workspace',
          objective: 'Prepare the repo and environment for implementation.',
          why_now: 'This unlocks the later delivery steps.',
        },
        {
          id: 'S2',
          title: 'Ship implementation',
          objective: 'Land the main change set.',
          why_now: 'This is the core delivery path.',
        },
      ],
    })

    expect(normalized).toEqual({
      kind: 'subtasks',
      cards: [
        {
          key: 'S1-Setup workspace',
          title: 'S1 / Setup workspace',
          body: 'Prepare the repo and environment for implementation.',
          meta: [{ label: 'Why now', value: 'This unlocks the later delivery steps.' }],
        },
        {
          key: 'S2-Ship implementation',
          title: 'S2 / Ship implementation',
          body: 'Land the main change set.',
          meta: [{ label: 'Why now', value: 'This is the core delivery path.' }],
        },
      ],
    })
  })

  it('keeps legacy slice payloads readable on transition read paths', () => {
    const normalized = normalizeSplitPayload({
      subtasks: [
        {
          order: 1,
          prompt: 'Setup repo',
          risk_reason: 'Environment setup is a dependency.',
          what_unblocks: 'Main implementation can start afterwards.',
        },
      ],
    })

    expect(normalized).toEqual({
      kind: 'subtasks',
      cards: [
        {
          key: '1-Setup repo',
          title: 'Slice 1',
          body: 'Setup repo',
          meta: [
            { label: 'Risk', value: 'Environment setup is a dependency.' },
            { label: 'Unblocks', value: 'Main implementation can start afterwards.' },
          ],
        },
      ],
    })
  })
})
