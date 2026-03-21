interface ElectronAPI {
  selectFolder: () => Promise<string | null>
  getAuthToken: () => Promise<string>
  getBackendPort: () => Promise<number>
  getAppVersion: () => Promise<string>
  setWindowTitle: (title: string) => void
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
