import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import { deriveMessagesV3ParityModel } from '../../src/features/conversation/components/v3/messagesV3.parityModel'

type ScenarioFixture = {
  id: string
  snapshot_v3: ThreadSnapshotV3
  expected: {
    parity_model: {
      visibleItemIds: string[]
      visibleItemKinds: string[]
      pendingRequestIds: string[]
      inlineUserInputItemIds: string[]
      showPlanReadyCard: boolean
      planReadySuppressionReason: string
      toolGroupCount: number
    }
  }
}

function loadParityFixtures(): ScenarioFixture[] {
  const candidatePaths = [
    resolve(
      process.cwd(),
      'docs',
      'thread-rework',
      'uiux',
      'artifacts',
      'parity-fixtures',
      'execution-audit-v3-parity-fixtures.json',
    ),
    resolve(
      process.cwd(),
      '..',
      'docs',
      'thread-rework',
      'uiux',
      'artifacts',
      'parity-fixtures',
      'execution-audit-v3-parity-fixtures.json',
    ),
  ]
  const fixturePath = candidatePaths.find((candidate) => existsSync(candidate))
  if (!fixturePath) {
    throw new Error('Parity fixture file not found')
  }
  const payload = JSON.parse(readFileSync(fixturePath, 'utf-8')) as {
    scenarios: ScenarioFixture[]
  }
  return payload.scenarios
}

describe('messagesV3 parity golden fixtures', () => {
  it('matches expected derived parity model for each fixture scenario', () => {
    const scenarios = loadParityFixtures()
    expect(scenarios.length).toBeGreaterThan(0)

    for (const scenario of scenarios) {
      const model = deriveMessagesV3ParityModel(scenario.snapshot_v3)
      const expected = scenario.expected.parity_model

      expect(model.visibleItemIds, `${scenario.id}: visibleItemIds`).toEqual(expected.visibleItemIds)
      expect(model.visibleItemKinds, `${scenario.id}: visibleItemKinds`).toEqual(expected.visibleItemKinds)
      expect(model.pendingRequestIds, `${scenario.id}: pendingRequestIds`).toEqual(
        expected.pendingRequestIds,
      )
      expect(model.inlineUserInputItemIds, `${scenario.id}: inlineUserInputItemIds`).toEqual(
        expected.inlineUserInputItemIds,
      )
      expect(model.showPlanReadyCard, `${scenario.id}: showPlanReadyCard`).toBe(
        expected.showPlanReadyCard,
      )
      expect(model.planReadySuppressionReason, `${scenario.id}: suppression`).toBe(
        expected.planReadySuppressionReason,
      )
      expect(model.toolGroupCount, `${scenario.id}: toolGroupCount`).toBe(expected.toolGroupCount)
    }
  })
})
