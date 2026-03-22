// @ts-check
/**
 * Manages the Python/FastAPI backend subprocess lifecycle.
 * Finds a free port, spawns the PyInstaller binary, health-polls,
 * and cleanly kills the process tree on shutdown.
 */

const { spawn } = require('child_process')
const net = require('net')
const path = require('path')
const { log } = require('./logger')

/** @type {import('child_process').ChildProcess | null} */
let backendProcess = null
/** @type {number | null} */
let backendPort = null
/** @type {boolean} */
let _isStopping = false
/** @type {((code: number | null, signal: string | null) => void) | null} */
let _onCrashCallback = null

/**
 * Bind a temporary TCP server to port 0 on 127.0.0.1
 * and return the OS-assigned port.
 * @returns {Promise<number>}
 */
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

/**
 * Resolve the path to the PyInstaller backend binary.
 * In packaged app: resources/backend/planningtree-server.exe
 * In dev: returns null (backend runs externally via scripts/dev.py).
 * @returns {string | null}
 */
function getBackendBinaryPath() {
  if (process.env.ELECTRON_DEV) return null

  const binaryName =
    process.platform === 'win32'
      ? 'planningtree-server.exe'
      : 'planningtree-server'
  return path.join(process.resourcesPath, 'backend', binaryName)
}

/**
 * Create a line-buffered handler for a readable stream.
 * Buffers chunks and emits complete lines to the callback.
 * Handles chunk boundaries that split mid-line.
 * @param {import('stream').Readable} stream
 * @param {(line: string) => void} onLine
 * @returns {{ flush: () => void }}
 */
function lineBuffer(stream, onLine) {
  let buffer = ''
  stream.on('data', (data) => {
    buffer += data.toString()
    const lines = buffer.split('\n')
    // Last element is either '' (if data ended with \n) or a partial line
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.length > 0) {
        onLine(line)
      }
    }
  })
  return {
    flush() {
      if (buffer.length > 0) {
        onLine(buffer)
        buffer = ''
      }
    },
  }
}

/**
 * Poll GET /health until it returns 200 or timeout expires.
 * Mirrors scripts/dev.py:302-312.
 * @param {number} port
 * @param {number} [timeoutMs=30000]
 * @returns {Promise<void>}
 */
async function waitForHealth(port, timeoutMs = 30000) {
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
 * Start the backend binary on a free port.
 * @param {string} authToken - per-launch auth token
 * @returns {Promise<void>}
 */
async function startBackend(authToken) {
  const binaryPath = getBackendBinaryPath()
  if (!binaryPath) {
    // Dev mode: backend is expected to be running via scripts/dev.py
    backendPort = Number(process.env.PLANNINGTREE_BACKEND_PORT || 8000)
    return
  }

  backendPort = await findFreePort()
  log('backend-manager', `Starting backend on port ${backendPort}`)

  _isStopping = false

  backendProcess = spawn(binaryPath, [], {
    env: {
      ...process.env,
      PLANNINGTREE_PORT: String(backendPort),
      PLANNINGTREE_AUTH_TOKEN: authToken,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  const stdoutBuf = lineBuffer(backendProcess.stdout, (line) => {
    log('backend', line)
  })
  const stderrBuf = lineBuffer(backendProcess.stderr, (line) => {
    log('backend', line)
  })

  backendProcess.on('exit', (code, signal) => {
    stdoutBuf.flush()
    stderrBuf.flush()
    log(
      'backend-manager',
      `Backend exited (code=${code}, signal=${signal})`,
    )
    if (!_isStopping && _onCrashCallback) {
      _onCrashCallback(code, signal)
    }
  })

  await waitForHealth(backendPort)
  log('backend-manager', `Backend healthy on port ${backendPort}`)
}

/**
 * Kill the backend process tree. Mirrors scripts/dev.py:286-299.
 * @returns {Promise<void>}
 */
async function stopBackend() {
  if (!backendProcess || backendProcess.exitCode !== null) return

  _isStopping = true
  log('backend-manager', 'Stopping backend...')

  if (process.platform === 'win32') {
    spawn('taskkill', ['/PID', String(backendProcess.pid), '/T', '/F'], {
      stdio: 'ignore',
    })
  } else {
    backendProcess.kill('SIGTERM')
  }

  // Wait up to 5s for graceful exit
  await Promise.race([
    new Promise((resolve) => backendProcess.on('exit', resolve)),
    new Promise((resolve) => setTimeout(resolve, 5000)),
  ])

  // Force kill if still alive
  if (backendProcess.exitCode === null) {
    try {
      backendProcess.kill('SIGKILL')
    } catch {
      // already dead
    }
  }

  backendProcess = null
}

/**
 * Register a callback invoked when the backend exits unexpectedly.
 * @param {((code: number | null, signal: string | null) => void) | null} fn
 */
function setOnCrashCallback(fn) {
  _onCrashCallback = fn
}

/** @returns {boolean} */
function isBackendRunning() {
  return backendProcess !== null && backendProcess.exitCode === null
}

/**
 * @returns {string} Full backend URL
 */
function getBackendUrl() {
  return `http://127.0.0.1:${backendPort}`
}

/** @returns {number | null} */
function getBackendPort() {
  return backendPort
}

module.exports = {
  startBackend,
  stopBackend,
  getBackendUrl,
  getBackendPort,
  setOnCrashCallback,
  isBackendRunning,
}
