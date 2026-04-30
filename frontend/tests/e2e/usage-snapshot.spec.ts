import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { APIRequestContext, Page } from '@playwright/test'
import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })
test.setTimeout(90_000)

type UsageSnapshotPayload = {
  updated_at: number
  days: Array<{
    day: string
    input_tokens: number
    cached_input_tokens: number
    output_tokens: number
    total_tokens: number
    agent_time_ms: number
    agent_runs: number
  }>
  totals: {
    last7_days_tokens: number
    last30_days_tokens: number
    average_daily_tokens: number
    cache_hit_rate_percent: number
    peak_day: string | null
    peak_day_tokens: number
  }
  top_models: Array<{
    model: string
    tokens: number
    share_percent: number
  }>
}

function buildSnapshotPayload(): UsageSnapshotPayload {
  return {
    updated_at: 1_710_000_000_000,
    days: [
      {
        day: '2026-04-01',
        input_tokens: 1200,
        cached_input_tokens: 250,
        output_tokens: 600,
        total_tokens: 1800,
        agent_time_ms: 90_000,
        agent_runs: 4,
      },
      {
        day: '2026-04-02',
        input_tokens: 1100,
        cached_input_tokens: 200,
        output_tokens: 550,
        total_tokens: 1650,
        agent_time_ms: 84_000,
        agent_runs: 3,
      },
      {
        day: '2026-04-03',
        input_tokens: 1400,
        cached_input_tokens: 350,
        output_tokens: 700,
        total_tokens: 2100,
        agent_time_ms: 110_000,
        agent_runs: 5,
      },
      {
        day: '2026-04-04',
        input_tokens: 1500,
        cached_input_tokens: 400,
        output_tokens: 720,
        total_tokens: 2220,
        agent_time_ms: 120_000,
        agent_runs: 5,
      },
      {
        day: '2026-04-05',
        input_tokens: 900,
        cached_input_tokens: 210,
        output_tokens: 460,
        total_tokens: 1360,
        agent_time_ms: 72_000,
        agent_runs: 3,
      },
      {
        day: '2026-04-06',
        input_tokens: 1250,
        cached_input_tokens: 300,
        output_tokens: 640,
        total_tokens: 1890,
        agent_time_ms: 95_000,
        agent_runs: 4,
      },
      {
        day: '2026-04-07',
        input_tokens: 1600,
        cached_input_tokens: 420,
        output_tokens: 780,
        total_tokens: 2380,
        agent_time_ms: 130_000,
        agent_runs: 6,
      },
    ],
    totals: {
      last7_days_tokens: 13_400,
      last30_days_tokens: 13_400,
      average_daily_tokens: 1914,
      cache_hit_rate_percent: 24.2,
      peak_day: '2026-04-07',
      peak_day_tokens: 2380,
    },
    top_models: [
      {
        model: 'gpt-5',
        tokens: 8600,
        share_percent: 64.2,
      },
      {
        model: 'gpt-4.1',
        tokens: 4800,
        share_percent: 35.8,
      },
    ],
  }
}

async function seedAttachedProject(
  page: Page,
  request: APIRequestContext,
  suffix: string,
): Promise<void> {
  const workspaceRoot = join(process.cwd(), 'tests', 'e2e', '.tmp', `usage-${suffix}-${Date.now()}`)
  await mkdir(workspaceRoot, { recursive: true })

  await page.goto('/')
  const attachResponse = await request.post('/v4/projects/attach', {
    data: { folder_path: workspaceRoot },
  })
  expect(attachResponse.ok()).toBeTruthy()
}

test('opens usage snapshot from sidebar and renders key usage blocks', async ({ page, request }) => {
  const snapshotPayload = buildSnapshotPayload()
  await page.route('**/v4/usage/local*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(snapshotPayload),
    })
  })

  await seedAttachedProject(page, request, 'success')
  await expect(page.getByRole('button', { name: /open usage snapshot/i })).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: /open usage snapshot/i }).click()
  await expect(page).toHaveURL(/\/usage-snapshot/)

  await expect(page.getByRole('heading', { name: 'Usage Snapshot' })).toBeVisible()
  await expect(page.locator('[aria-label="Usage summary"]')).toBeVisible()
  await expect(page.locator('svg[aria-label="7-day token chart"]')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Last 7 days' })).toBeVisible()
  await expect(page.getByText('Top models')).toBeVisible()

  const refreshButton = page.getByTestId('usage-refresh-button')
  await expect(refreshButton).toBeVisible()
  await expect(refreshButton).toBeEnabled()
})

test('keeps snapshot content visible and shows non-blocking error when refresh fails', async ({
  page,
  request,
}) => {
  const snapshotPayload = buildSnapshotPayload()
  let shouldFailUsageRequest = false
  await page.route('**/v4/usage/local*', async (route) => {
    if (shouldFailUsageRequest) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'internal_error',
          message: 'simulated usage refresh failure',
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(snapshotPayload),
    })
  })

  await seedAttachedProject(page, request, 'error')
  await expect(page.getByRole('button', { name: /open usage snapshot/i })).toBeVisible({
    timeout: 30_000,
  })
  await page.getByRole('button', { name: /open usage snapshot/i }).click()
  await expect(page).toHaveURL(/\/usage-snapshot/)

  await expect(page.getByTestId('usage-snapshot-content')).toBeVisible()
  shouldFailUsageRequest = true
  await page.getByTestId('usage-refresh-button').click()

  await expect(page.getByTestId('usage-snapshot-error-banner')).toBeVisible()
  await expect(page.getByTestId('usage-snapshot-content')).toBeVisible()
})
