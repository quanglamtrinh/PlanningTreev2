// @ts-check
const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron')
const crypto = require('crypto')
const path = require('path')
const { initLogger, log, getLogPath } = require('./logger')
const {
  startBackend,
  stopBackend,
  getBackendUrl,
  getBackendPort,
  setOnCrashCallback,
} = require('./backend-manager')
const windowState = require('./window-state')
const { buildMenu } = require('./app-menu')

const IS_DEV = !!process.env.ELECTRON_DEV

/** Per-launch auth token — generated once, shared with backend + renderer. */
const AUTH_TOKEN = IS_DEV ? '' : crypto.randomUUID()

/** @type {BrowserWindow | null} */
let mainWindow = null
let _isQuitting = false
let _isRestarting = false

// ---------------------------------------------------------------------------
// Single-instance guard
// ---------------------------------------------------------------------------

const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.focus()
    }
  })

  // ---------------------------------------------------------------------------
  // Window management
  // ---------------------------------------------------------------------------

  function createWindow() {
    const state = windowState.loadWindowState()

    /** @type {Electron.BrowserWindowConstructorOptions} */
    const opts = {
      width: state.width,
      height: state.height,
      minWidth: 900,
      minHeight: 600,
      title: 'PlanningTree',
      backgroundColor: '#1a1a2e',
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    }
    if (state.x !== undefined && state.y !== undefined) {
      opts.x = state.x
      opts.y = state.y
    }

    mainWindow = new BrowserWindow(opts)

    if (state.isMaximized) {
      mainWindow.maximize()
    }

    // Window state persistence
    mainWindow.on('resize', () => windowState.saveWindowState(mainWindow))
    mainWindow.on('move', () => windowState.saveWindowState(mainWindow))
    mainWindow.on('close', () =>
      windowState.saveWindowState(mainWindow, { immediate: true }),
    )
    mainWindow.on('closed', () => {
      mainWindow = null
    })

    // Context menu: replace default Chromium menu with minimal native menu
    mainWindow.webContents.on('context-menu', (_event, params) => {
      /** @type {Electron.MenuItemConstructorOptions[]} */
      const template = []

      if (params.isEditable) {
        template.push({ role: 'cut' }, { role: 'copy' }, { role: 'paste' })
      } else if (params.selectionText) {
        template.push({ role: 'copy' })
      }

      if (IS_DEV) {
        if (template.length > 0) template.push({ type: 'separator' })
        template.push({
          label: 'Inspect Element',
          click: () =>
            mainWindow.webContents.inspectElement(params.x, params.y),
        })
      }

      if (template.length > 0) {
        Menu.buildFromTemplate(template).popup()
      }
    })

    // Keyboard shortcut hardening
    mainWindow.webContents.on('before-input-event', (event, input) => {
      if (input.type !== 'keyDown') return

      const ctrl = input.control || input.meta
      const key = input.key.toLowerCase()

      // Block Ctrl+W in all modes (single-window app)
      if (ctrl && key === 'w') {
        event.preventDefault()
        return
      }

      if (!IS_DEV) {
        // Block Ctrl+R, Ctrl+Shift+R, F5 (accidental reload)
        if (ctrl && key === 'r') {
          event.preventDefault()
          return
        }
        if (input.key === 'F5') {
          event.preventDefault()
          return
        }
        // Block Ctrl+Shift+I (devtools)
        if (ctrl && input.shift && key === 'i') {
          event.preventDefault()
          return
        }
      }
    })
  }

  // ---------------------------------------------------------------------------
  // Splash screen
  // ---------------------------------------------------------------------------

  function loadSplash(message = 'Starting backend server...') {
    if (!mainWindow) return
    const html = `
      <!DOCTYPE html>
      <html><head><meta charset="utf-8"><style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
          background: #1a1a2e; color: #e0e0e0;
          font-family: system-ui, -apple-system, sans-serif;
          display: flex; align-items: center; justify-content: center;
          height: 100vh; flex-direction: column; gap: 24px;
          -webkit-app-region: drag;
        }
        h1 { font-size: 28px; font-weight: 600; color: #fff; }
        .spinner {
          width: 36px; height: 36px;
          border: 3px solid rgba(255,255,255,0.15);
          border-top-color: #4fc3f7;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        p { font-size: 14px; color: #aaa; }
      </style></head><body>
        <h1>PlanningTree</h1>
        <div class="spinner"></div>
        <p>${message}</p>
      </body></html>
    `
    mainWindow.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(html)}`,
    )
  }

  // ---------------------------------------------------------------------------
  // IPC handlers
  // ---------------------------------------------------------------------------

  function registerIpcHandlers() {
    ipcMain.handle('dialog:selectFolder', async () => {
      if (!mainWindow) return null
      const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory', 'createDirectory'],
        title: 'Choose Workspace Folder',
      })
      if (result.canceled || result.filePaths.length === 0) return null
      return result.filePaths[0]
    })

    ipcMain.handle('app:getAuthToken', () => AUTH_TOKEN)
    ipcMain.handle('app:getBackendPort', () => getBackendPort())
    ipcMain.handle('app:getAppVersion', () => app.getVersion())

    ipcMain.on('app:setWindowTitle', (_event, title) => {
      if (mainWindow && typeof title === 'string') {
        const truncated = title.length > 80 ? title.slice(0, 77) + '...' : title
        mainWindow.setTitle(truncated || 'PlanningTree')
      }
    })
  }

  // ---------------------------------------------------------------------------
  // Backend crash recovery
  // ---------------------------------------------------------------------------

  async function handleBackendCrash(code, signal) {
    if (_isQuitting || _isRestarting) return
    _isRestarting = true

    log('main', `Backend crashed unexpectedly (code=${code}, signal=${signal})`)

    const logPath = getLogPath()
    const result = await dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: 'PlanningTree — Backend Crashed',
      message: 'The backend server stopped unexpectedly.',
      detail: `Exit code: ${code}\nCheck logs at: ${logPath}`,
      buttons: ['Restart', 'Quit'],
      defaultId: 0,
      cancelId: 1,
    })

    if (result.response === 1) {
      app.quit()
      return
    }

    // Restart loop — retry until success or user quits
    while (true) {
      loadSplash('Restarting backend server...')

      try {
        await startBackend(AUTH_TOKEN)
        setOnCrashCallback(handleBackendCrash)
        mainWindow.loadURL(getBackendUrl())
        _isRestarting = false
        log('main', 'Backend restarted successfully')
        return
      } catch (err) {
        log('main', `Backend restart failed: ${err.message}`)
        const retry = await dialog.showMessageBox(mainWindow, {
          type: 'error',
          title: 'PlanningTree — Restart Failed',
          message: `Failed to restart the backend server.`,
          detail: `${err.message}\n\nCheck logs at: ${logPath}`,
          buttons: ['Retry', 'Quit'],
          defaultId: 0,
          cancelId: 1,
        })
        if (retry.response === 1) {
          app.quit()
          return
        }
        // Loop continues — retry
      }
    }
  }

  // ---------------------------------------------------------------------------
  // App lifecycle
  // ---------------------------------------------------------------------------

  async function loadApp() {
    if (IS_DEV) {
      const devUrl =
        process.env.ELECTRON_DEV_URL || 'http://127.0.0.1:5174'
      mainWindow.loadURL(devUrl)
      mainWindow.webContents.openDevTools()
    } else {
      mainWindow.loadURL(getBackendUrl())
    }
  }

  app.whenReady().then(async () => {
    initLogger(app.getPath('userData'))
    windowState.init(app.getPath('userData'))
    process.env.PLANNINGTREE_VERSION = app.getVersion()
    log('main', `PlanningTree ${app.getVersion()} starting (dev=${IS_DEV})`)

    registerIpcHandlers()
    createWindow()
    Menu.setApplicationMenu(
      buildMenu({ mainWindow, isDev: IS_DEV, logPath: getLogPath() }),
    )

    if (!IS_DEV) {
      loadSplash()

      try {
        await startBackend(AUTH_TOKEN)
        setOnCrashCallback(handleBackendCrash)
      } catch (err) {
        log('main', `Backend startup failed: ${err.message}`)
        dialog.showErrorBox(
          'PlanningTree — Backend Error',
          `Failed to start the backend server:\n\n${err.message}\n\nThe application will quit.`,
        )
        app.quit()
        return
      }
    }

    await loadApp()
    log('main', 'App loaded')
  })

  app.on('window-all-closed', () => {
    app.quit()
  })

  app.on('before-quit', (e) => {
    if (_isQuitting) return
    e.preventDefault()
    _isQuitting = true
    log('main', 'Quitting — stopping backend...')
    stopBackend().finally(() => app.quit())
  })
}
