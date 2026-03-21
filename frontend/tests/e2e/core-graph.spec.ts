import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'

test('attaches project folders, renders the graph shell, and opens the breadcrumb stub', async ({
  page,
  request,
}) => {
  const workspaceRoot = join(process.cwd(), 'tests', 'e2e', '.tmp', `workspace-${Date.now()}`)
  const newestWorkspaceRoot = join(process.cwd(), 'tests', 'e2e', '.tmp', `workspace-${Date.now()}-latest`)

  await mkdir(workspaceRoot, { recursive: true })
  await mkdir(newestWorkspaceRoot, { recursive: true })
  await page.goto('/')
  const initialProjectResponse = await request.post('/v1/projects/attach', {
    data: { folder_path: workspaceRoot },
  })
  expect(initialProjectResponse.ok()).toBeTruthy()
  const newestProjectResponse = await request.post('/v1/projects/attach', {
    data: { folder_path: newestWorkspaceRoot },
  })
  expect(newestProjectResponse.ok()).toBeTruthy()
  const newestSnapshot = (await newestProjectResponse.json()) as {
    project: { name: string }
    tree_state: { root_node_id: string }
  }

  await page.evaluate(() => {
    window.localStorage.removeItem('planningtree.active-project-id')
  })
  await page.reload()

  await expect(page.getByText('Projects')).toBeVisible()
  await expect(page.getByRole('button', { name: newestSnapshot.project.name, exact: true })).toBeVisible()
  await expect(page.getByTestId(`graph-node-${newestSnapshot.tree_state.root_node_id}`)).toBeVisible()

  await page.getByRole('button', { name: 'Node actions' }).click()
  await page.getByRole('button', { name: 'Create Child' }).click()
  await expect(page.getByRole('button', { name: /1\.1 New Node/ })).toBeVisible()

  await page.getByRole('button', { name: 'Node actions' }).last().click()
  await page.getByRole('button', { name: 'Open Breadcrumb' }).click()
  await expect(page.getByTestId('breadcrumb-thread-pane')).toBeVisible()
  await expect(page.getByText('New Node')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to Graph' })).toBeVisible()
})
