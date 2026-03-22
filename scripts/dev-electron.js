#!/usr/bin/env node
// @ts-check
/**
 * Electron development launcher.
 *
 * Reuses scripts/dev.py for backend + frontend startup (venv, deps,
 * port check, health poll, process cleanup), then launches Electron
 * with ELECTRON_DEV=1 once both servers are ready.
 */

const { spawn } = require('child_process')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const BACKEND_PORT = 8000
const FRONTEND_PORT = 5174

/** @type {import('child_process').ChildProcess[]} */
const procs = []
let shuttingDown = false

function cleanup() {
  if (shuttingDown) return
  shuttingDown = true
  console.log('[dev-electron] Shutting down...')
  for (const proc of procs) {
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/PID', String(proc.pid), '/T', '/F'], {
          stdio: 'ignore',
        })
      } else {
        proc.kill('SIGTERM')
      }
    } catch {
      // already dead
    }
  }
  // Give processes a moment to exit, then force-quit
  setTimeout(() => process.exit(0), 2000)
}

process.on('SIGINT', cleanup)
process.on('SIGTERM', cleanup)

/**
 * Wait for an HTTP endpoint to respond with 200.
 * @param {string} url
 * @param {number} timeoutMs
 * @returns {Promise<void>}
 */
async function waitForReady(url, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(2000) })
      if (res.ok) return
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error(`${url} did not become ready within ${timeoutMs}ms`)
}

async function main() {
  // 1. Start backend + frontend via scripts/dev.py
  //    dev.py handles venv, deps, port check, health poll, process groups.
  console.log('[dev-electron] Starting backend + frontend via scripts/dev.py...')
  const devPy = spawn('python', ['scripts/dev.py'], {
    cwd: ROOT,
    stdio: 'inherit',
  })
  procs.push(devPy)

  devPy.on('exit', (code) => {
    if (!shuttingDown) {
      console.error(`[dev-electron] dev.py exited unexpectedly (code=${code})`)
      cleanup()
    }
  })

  // 2. Wait for both servers
  console.log('[dev-electron] Waiting for backend + frontend...')
  try {
    await waitForReady(`http://127.0.0.1:${BACKEND_PORT}/health`, 60000)
    console.log('[dev-electron] Backend ready.')
    await waitForReady(`http://127.0.0.1:${FRONTEND_PORT}/`, 60000)
    console.log('[dev-electron] Frontend ready.')
  } catch (err) {
    console.error(`[dev-electron] ${err.message}`)
    cleanup()
    return
  }

  // 3. Launch Electron
  console.log('[dev-electron] Launching Electron...')
  let electronPath
  try {
    electronPath = require('electron')
  } catch {
    console.error(
      '[dev-electron] Electron not installed. Run: npm install --save-dev electron',
    )
    cleanup()
    return
  }

  const electronProc = spawn(electronPath, ['.'], {
    cwd: ROOT,
    env: {
      ...process.env,
      ELECTRON_DEV: '1',
      PLANNINGTREE_BACKEND_PORT: String(BACKEND_PORT),
    },
    stdio: 'inherit',
  })
  procs.push(electronProc)

  electronProc.on('exit', () => {
    console.log('[dev-electron] Electron closed.')
    cleanup()
  })
}

main().catch((err) => {
  console.error('[dev-electron] Fatal:', err)
  cleanup()
})
