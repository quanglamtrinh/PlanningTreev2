#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const ROOT = process.cwd()

function walk(dir) {
  const rows = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const target = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      rows.push(...walk(target))
      continue
    }
    if (entry.isFile() && (target.endsWith('.ts') || target.endsWith('.tsx'))) {
      rows.push(target)
    }
  }
  return rows
}

function collectViolations(files, checks) {
  const violations = []
  for (const file of files) {
    const content = fs.readFileSync(file, 'utf8')
    for (const check of checks) {
      if (check.pattern.test(content)) {
        violations.push({
          file,
          reason: check.reason,
        })
      }
    }
  }
  return violations
}

const workflowFiles = walk(path.join(ROOT, 'src', 'features', 'workflow_v2'))
const sessionFiles = walk(path.join(ROOT, 'src', 'features', 'session_v2'))

const workflowChecks = [
  {
    pattern: /features\/session_v2|session_v2\/store\/threadSessionStore|openThreadEventsStreamV2/,
    reason: 'workflow_v2 must not mutate/read session transcript ownership paths.',
  },
]

const sessionChecks = [
  {
    pattern: /features\/workflow_v2\/api\/client|workflow_v2\/store\/workflowStateStoreV2|openWorkflowEventsStreamV2/,
    reason: 'session_v2 must not depend on workflow SSE/store ownership paths.',
  },
]

const violations = [
  ...collectViolations(workflowFiles, workflowChecks),
  ...collectViolations(sessionFiles, sessionChecks),
]

if (violations.length > 0) {
  const lines = violations.map((entry) => `- ${path.relative(ROOT, entry.file)}: ${entry.reason}`)
  process.stderr.write(
    ['Stream boundary check failed.', ...lines, 'Fix imports/calls crossing workflow/session stream boundaries.'].join('\n') + '\n',
  )
  process.exit(1)
}

process.stdout.write('Stream boundary check passed.\n')
