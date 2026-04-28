import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'

test.setTimeout(90_000)

test('attaches project folders, renders the graph shell, and opens the breadcrumb stub', async ({
  page,
  request,
}) => {
  const workspaceRoot = join(process.cwd(), 'tests', 'e2e', '.tmp', `workspace-${Date.now()}-task`)

  await mkdir(workspaceRoot, { recursive: true })
  await page.goto('/')

  const attachProjectResponse = await request.post('/v3/projects/attach', {
    data: { folder_path: workspaceRoot },
  })
  expect(attachProjectResponse.ok()).toBeTruthy()
  const attachedSnapshot = (await attachProjectResponse.json()) as {
    project: { id: string; name: string }
  }

  await page.evaluate((projectId) => {
    window.localStorage.setItem('planningtree.active-project-id', projectId)
  }, attachedSnapshot.project.id)

  const snapshotLoaded = page
    .waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        response.url().includes(`/v3/projects/${attachedSnapshot.project.id}/snapshot`),
      { timeout: 45_000 },
    )
    .catch(() => null)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await snapshotLoaded
  await expect(page.locator('[data-testid^="graph-node-"]').first()).toBeVisible({
    timeout: 45_000,
  })

  await page.getByRole('button', { name: 'Node actions' }).click()
  await page.getByRole('button', { name: 'Create A Task' }).click()
  await expect(page.getByRole('heading', { name: 'Create A Task' })).toBeVisible()
  const taskTitle = 'Smoke test task for baseline e2e'
  await page.locator('#create-task-description').fill(taskTitle)
  await page.getByRole('button', { name: 'Confirm Task' }).click()

  const backToGraphButton = page.getByRole('button', { name: 'Back to Graph' })
  const newTaskNode = page
    .locator(`[data-testid^="graph-node-"][data-node-title="${taskTitle}"]`)
    .first()

  const waitDeadline = Date.now() + 60_000
  while (Date.now() < waitDeadline) {
    const nodeVisible = await newTaskNode.isVisible().catch(() => false)
    if (nodeVisible) {
      break
    }
    const isInBreadcrumb = await backToGraphButton.isVisible().catch(() => false)
    if (isInBreadcrumb) {
      await backToGraphButton.click()
    }
    await page.waitForTimeout(300)
  }

  await expect(newTaskNode).toBeVisible({ timeout: 5_000 })
  await newTaskNode.getByRole('button', { name: 'Open in Breadcrumb' }).click()
  await expect(page.getByTestId('breadcrumb-thread-pane')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('heading', { name: taskTitle })).toBeVisible({ timeout: 30_000 })
})
