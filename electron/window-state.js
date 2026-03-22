// @ts-check
/**
 * Persists and restores BrowserWindow size/position across sessions.
 * Saves to {userData}/window-state.json.
 */

const fs = require('fs')
const path = require('path')
const { screen } = require('electron')

const DEFAULTS = { width: 1400, height: 900 }
const MIN_VISIBLE_PX = 100
const DEBOUNCE_MS = 300

/** @type {string} */
let stateFilePath = ''
/** @type {ReturnType<typeof setTimeout> | null} */
let saveTimer = null

/**
 * @param {string} userDataPath - app.getPath('userData')
 */
function init(userDataPath) {
  stateFilePath = path.join(userDataPath, 'window-state.json')

  // Ensure parent directory exists (first run or custom path)
  fs.mkdirSync(userDataPath, { recursive: true })
}

/**
 * Load saved window state. Returns defaults if file missing or invalid.
 * Validates that saved bounds are visible on a connected display.
 * @returns {{ x?: number, y?: number, width: number, height: number, isMaximized: boolean }}
 */
function loadWindowState() {
  try {
    const raw = fs.readFileSync(stateFilePath, 'utf-8')
    const state = JSON.parse(raw)

    const width = typeof state.width === 'number' && state.width >= 400 ? state.width : DEFAULTS.width
    const height = typeof state.height === 'number' && state.height >= 300 ? state.height : DEFAULTS.height
    const isMaximized = state.isMaximized === true

    if (typeof state.x !== 'number' || typeof state.y !== 'number') {
      return { width, height, isMaximized }
    }

    // Validate bounds are actually visible on a connected display
    const bounds = { x: state.x, y: state.y, width, height }
    const display = screen.getDisplayMatching(bounds)
    const wa = display.workArea

    // Compute intersection
    const overlapX = Math.max(
      0,
      Math.min(bounds.x + bounds.width, wa.x + wa.width) - Math.max(bounds.x, wa.x),
    )
    const overlapY = Math.max(
      0,
      Math.min(bounds.y + bounds.height, wa.y + wa.height) - Math.max(bounds.y, wa.y),
    )

    if (overlapX < MIN_VISIBLE_PX || overlapY < MIN_VISIBLE_PX) {
      // Window is effectively off-screen; discard position, keep size
      return { width, height, isMaximized }
    }

    return { x: state.x, y: state.y, width, height, isMaximized }
  } catch {
    return { ...DEFAULTS, isMaximized: false }
  }
}

/**
 * Save window state. Debounced to avoid excessive writes during resize drag.
 * Only saves non-maximized bounds (maximized bounds are screen bounds, not user preference).
 * @param {import('electron').BrowserWindow} win
 * @param {{ immediate?: boolean }} [opts]
 */
function saveWindowState(win, opts) {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }

  const doSave = () => {
    try {
      const isMaximized = win.isMaximized()
      const bounds = isMaximized ? {} : win.getBounds()
      const state = {
        ...bounds,
        isMaximized,
      }

      // If maximized, preserve the last known normal bounds from the existing file
      if (isMaximized) {
        try {
          const existing = JSON.parse(fs.readFileSync(stateFilePath, 'utf-8'))
          state.x = existing.x
          state.y = existing.y
          state.width = existing.width
          state.height = existing.height
        } catch {
          state.width = DEFAULTS.width
          state.height = DEFAULTS.height
        }
      }

      fs.writeFileSync(stateFilePath, JSON.stringify(state), 'utf-8')
    } catch (err) {
      process.stderr.write(`[window-state] Failed to save: ${err.message}\n`)
    }
  }

  if (opts?.immediate) {
    doSave()
  } else {
    saveTimer = setTimeout(doSave, DEBOUNCE_MS)
  }
}

module.exports = { init: init, loadWindowState, saveWindowState }
