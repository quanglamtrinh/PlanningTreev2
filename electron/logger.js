// @ts-check
/**
 * File-based logger for the Electron main process.
 * Writes timestamped lines to {userData}/planningtree.log.
 */

const fs = require('fs')
const path = require('path')

const MAX_LOG_BYTES = 2 * 1024 * 1024 // 2 MB
const KEEP_LINES = 5000

/** @type {fs.WriteStream | null} */
let logStream = null
/** @type {string} */
let logFilePath = ''

/**
 * Initialize the logger. Must be called after app.whenReady().
 * @param {string} userDataPath - app.getPath('userData')
 */
function initLogger(userDataPath) {
  logFilePath = path.join(userDataPath, 'planningtree.log')

  // Ensure parent directory exists (first run or custom path)
  fs.mkdirSync(userDataPath, { recursive: true })

  // Truncate if oversized
  try {
    const stat = fs.statSync(logFilePath)
    if (stat.size > MAX_LOG_BYTES) {
      const content = fs.readFileSync(logFilePath, 'utf-8')
      const lines = content.split('\n')
      const trimmed = lines.slice(-KEEP_LINES).join('\n')
      fs.writeFileSync(logFilePath, trimmed, 'utf-8')
    }
  } catch {
    // File doesn't exist yet — that's fine
  }

  logStream = fs.createWriteStream(logFilePath, { flags: 'a' })
  logStream.on('error', (err) => {
    process.stderr.write(`[logger] Write stream error: ${err.message}\n`)
    logStream = null
  })
  log('logger', `Log file: ${logFilePath}`)
}

/**
 * Write a timestamped log line.
 * @param {string} tag
 * @param {string} message
 */
function log(tag, message) {
  const ts = new Date().toISOString()
  const line = `${ts} [${tag}] ${message}\n`
  process.stdout.write(line)
  if (logStream) {
    logStream.write(line)
  }
}

/** @returns {string} */
function getLogPath() {
  return logFilePath
}

/** @returns {fs.WriteStream | null} */
function getLogStream() {
  return logStream
}

module.exports = { initLogger, log, getLogPath, getLogStream }
