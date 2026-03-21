// @ts-check
/**
 * Validates the PyInstaller build by:
 * 1. Checking the backend binary exists
 * 2. Checking the binary is not stale relative to frontend/dist
 * 3. Starting the binary on a random port
 * 4. Health-checking GET /health
 * 5. Checking GET / serves React HTML
 * 6. Killing the process
 *
 * This script does NOT rebuild anything — it only validates.
 * Use `python scripts/build-backend.py` to produce a fresh build.
 */

const { spawn, execSync } = require('child_process')
const net = require('net')
const path = require('path')
const fs = require('fs')

const ROOT = path.resolve(__dirname, '..')
const FRONTEND_DIST = path.join(ROOT, 'frontend', 'dist')
const BINARY_DIR = path.join(ROOT, 'build', 'dist', 'planningtree-server')
const BINARY_NAME =
  process.platform === 'win32'
    ? 'planningtree-server.exe'
    : 'planningtree-server'
const BINARY_PATH = path.join(BINARY_DIR, BINARY_NAME)

let backendProcess = null

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

function killBackend() {
  if (!backendProcess || backendProcess.exitCode !== null) return

  if (process.platform === 'win32') {
    try {
      execSync(`taskkill /PID ${backendProcess.pid} /T /F`, {
        stdio: 'ignore',
      })
    } catch {
      // already dead
    }
  } else {
    backendProcess.kill('SIGTERM')
  }
  backendProcess = null
}

async function waitForHealth(port, timeoutMs = 20000) {
  const url = `http://127.0.0.1:${port}/health`
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(2000) })
      if (res.ok) return
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`Backend did not become healthy within ${timeoutMs}ms`)
}

/**
 * Walk a directory tree and return the most recent mtime (ms since epoch).
 * @param {string} dirPath
 * @returns {number}
 */
function newestMtime(dirPath) {
  let newest = 0
  const entries = fs.readdirSync(dirPath, { withFileTypes: true })
  for (const entry of entries) {
    const full = path.join(dirPath, entry.name)
    if (entry.isDirectory()) {
      newest = Math.max(newest, newestMtime(full))
    } else {
      newest = Math.max(newest, fs.statSync(full).mtimeMs)
    }
  }
  return newest
}

async function main() {
  let passed = 0
  let failed = 0

  function pass(msg) {
    console.log(`  PASS  ${msg}`)
    passed++
  }
  function fail(msg) {
    console.log(`  FAIL  ${msg}`)
    failed++
  }

  console.log('=== PlanningTree Build Validation ===\n')

  // 1. Check binary exists
  console.log('1. Checking backend binary...')
  if (fs.existsSync(BINARY_PATH)) {
    pass(`Binary exists: ${BINARY_PATH}`)
  } else {
    fail(
      `Binary not found: ${BINARY_PATH}\n         Run "python scripts/build-backend.py" first`,
    )
    console.log(`\n=== ${passed} passed, ${failed} failed ===`)
    process.exit(1)
  }

  // 2. Staleness check — binary must be newer than frontend/dist
  console.log('2. Checking binary freshness...')
  if (fs.existsSync(FRONTEND_DIST)) {
    const frontendNewest = newestMtime(FRONTEND_DIST)
    const binaryMtime = fs.statSync(BINARY_PATH).mtimeMs
    if (binaryMtime >= frontendNewest) {
      pass('Binary is newer than frontend/dist')
    } else {
      const ageSec = Math.round((frontendNewest - binaryMtime) / 1000)
      fail(
        `Binary is ${ageSec}s older than frontend/dist — frontend changes are not bundled.\n         Run "python scripts/build-backend.py" to rebuild.`,
      )
    }
  } else {
    fail(
      'frontend/dist not found — run "python scripts/build-backend.py" to build everything',
    )
  }

  // 3. Start binary on random port
  console.log('3. Starting backend binary...')
  let port
  try {
    port = await findFreePort()
    backendProcess = spawn(BINARY_PATH, [], {
      env: { ...process.env, PLANNINGTREE_PORT: String(port) },
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    backendProcess.on('exit', (code) => {
      if (code !== null && code !== 0) {
        console.log(`   Backend exited with code ${code}`)
      }
    })

    await waitForHealth(port)
    pass(`Backend started on port ${port}`)
  } catch (err) {
    fail(`Backend failed to start: ${err.message}`)
    killBackend()
    console.log(`\n=== ${passed} passed, ${failed} failed ===`)
    process.exit(1)
  }

  // 4. Health check
  console.log('4. Health check...')
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health`)
    const data = await res.json()
    if (res.ok && data.status === 'ok') {
      pass('GET /health returned 200 with status ok')
    } else {
      fail(`GET /health returned ${res.status}: ${JSON.stringify(data)}`)
    }
  } catch (err) {
    fail(`GET /health failed: ${err.message}`)
  }

  // 5. Index page serves React HTML
  console.log('5. Index page check...')
  try {
    const res = await fetch(`http://127.0.0.1:${port}/`)
    const html = await res.text()
    if (res.ok && html.includes('id="root"')) {
      pass('GET / serves React HTML with root div')
    } else {
      fail(
        `GET / returned ${res.status}, root div ${html.includes('id="root"') ? 'found' : 'missing'}`,
      )
    }
  } catch (err) {
    fail(`GET / failed: ${err.message}`)
  }

  // 6. Cleanup
  console.log('6. Cleanup...')
  killBackend()
  pass('Backend process killed')

  console.log(`\n=== ${passed} passed, ${failed} failed ===`)
  process.exit(failed > 0 ? 1 : 0)
}

process.on('exit', killBackend)
process.on('SIGINT', () => {
  killBackend()
  process.exit(1)
})

main().catch((err) => {
  console.error(err)
  killBackend()
  process.exit(1)
})
