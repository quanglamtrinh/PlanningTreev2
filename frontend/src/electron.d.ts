interface ElectronAPI {
  selectFolder: () => Promise<string | null>
  getAuthToken: () => Promise<string>
  getBackendPort: () => Promise<number>
  getAppVersion: () => Promise<string>
  setWindowTitle: (title: string) => void
  logDebug?: (tag: string, message: string, details?: Record<string, unknown>) => void
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
