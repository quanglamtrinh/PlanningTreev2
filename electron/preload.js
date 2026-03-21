// @ts-check
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  /** Open native folder picker. Returns absolute path or null if cancelled. */
  selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),
  /** Get the per-launch auth token for API requests. */
  getAuthToken: () => ipcRenderer.invoke('app:getAuthToken'),
  /** Get the backend port (for SSE or debugging). */
  getBackendPort: () => ipcRenderer.invoke('app:getBackendPort'),
  /** Get the app version from package.json. */
  getAppVersion: () => ipcRenderer.invoke('app:getAppVersion'),
  /** Set the window title bar text. */
  setWindowTitle: (/** @type {string} */ title) =>
    ipcRenderer.send('app:setWindowTitle', title),
  /** Feature-detection flag for renderer code. */
  isElectron: true,
})
