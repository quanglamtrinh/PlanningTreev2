import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'

test('creates a project, renders the graph shell, and opens the breadcrumb stub', async ({
  page,
  request,
}) => {
  const workspaceRoot = join(process.cwd(), 'tests', 'e2e', '.tmp', `workspace-${Date.now()}`)
  const projectName = `Phase3-${Date.now()}`
  const newestProjectName = `${projectName}-Latest`

  await mkdir(workspaceRoot, { recursive: true })
  await page.goto('/')

  const setupHeading = page.getByRole('heading', { name: 'Choose a base workspace folder' })
  if ((await setupHeading.count()) > 0) {
    await page.getByLabel('Base workspace root').fill(workspaceRoot)
    await page.getByRole('button', { name: 'Save Workspace' }).click()
  } else {
    const workspaceResponse = await request.patch('/v1/settings/workspace', {
      data: { base_workspace_root: workspaceRoot },
    })
    expect(workspaceResponse.ok()).toBeTruthy()
    await page.reload()
  }

  await page.getByLabel('Name').fill(projectName)
  await page.getByLabel('Root goal').fill('Ship the legacy-style phase 3 graph')
  await page.getByRole('button', { name: /^Create$/ }).click()

  const newestProjectResponse = await request.post('/v1/projects', {
    data: {
      name: newestProjectName,
      root_goal: 'Make sure the newest project auto-loads with its root graph node visible.',
    },
  })
  expect(newestProjectResponse.ok()).toBeTruthy()
  const newestSnapshot = (await newestProjectResponse.json()) as {
    tree_state: { root_node_id: string }
  }

  await page.evaluate(() => {
    window.localStorage.removeItem('planningtree.active-project-id')
  })
  await page.reload()

  await expect(page.getByText('Graph Workspace')).toBeVisible()
  await expect(page.getByRole('heading', { name: newestProjectName, exact: true })).toBeVisible()
  await expect(page.getByTestId(`graph-node-${newestSnapshot.tree_state.root_node_id}`)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create Child' })).toBeVisible()

  await page.getByRole('button', { name: 'Create Child' }).evaluate((element: HTMLButtonElement) => {
    element.click()
  })
  await expect(page.getByRole('textbox', { name: 'Title' })).toHaveValue('New Node')

  await page.getByLabel('Title').fill('Implement graph shell')
  await page.getByLabel('Description').fill('Port the legacy UI treatment into the rebuild.')
  await page.getByLabel('Description').press('Tab')
  await expect(page.getByText('All changes saved')).toBeVisible()

  await page.getByRole('button', { name: 'Open Breadcrumb' }).evaluate((element: HTMLButtonElement) => {
    element.click()
  })
  await expect(page.getByText('Breadcrumb Chat arrives next')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to Graph' })).toBeVisible()
})
