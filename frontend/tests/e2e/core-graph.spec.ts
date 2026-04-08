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

  const attachProjectResponse = await request.post('/v1/projects/attach', {
    data: { folder_path: workspaceRoot },
  })
  expect(attachProjectResponse.ok()).toBeTruthy()
  const attachedSnapshot = (await attachProjectResponse.json()) as {
    project: { id: string; name: string }
    tree_state: { root_node_id: string }
  }

  await page.evaluate((projectId) => {
    window.localStorage.setItem('planningtree.active-project-id', projectId)
  }, attachedSnapshot.project.id)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await expect(page.getByTestId(`graph-node-${attachedSnapshot.tree_state.root_node_id}`)).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: 'Node actions' }).click()
  await page.getByRole('button', { name: 'Create A Task' }).click()
  await expect(page.getByRole('heading', { name: 'Create A Task' })).toBeVisible()
  await page.locator('#create-task-description').fill('Smoke test task for baseline e2e')
  await page.getByRole('button', { name: 'Confirm Task' }).click()

  // Create A Task currently auto-opens breadcrumb for the newly created task.
  await expect(page.getByTestId('breadcrumb-thread-pane')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'New Task' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to Graph' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to Graph' }).click()

  const newTaskNode = page
    .locator('[data-testid^="graph-node-"][data-node-title="New Task"]')
    .first()
  await expect(newTaskNode).toBeVisible()
  await newTaskNode.getByRole('button', { name: 'Open in Breadcrumb' }).click()
  await expect(page.getByTestId('breadcrumb-thread-pane')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'New Task' })).toBeVisible()
})
