import { matchPath, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useCodexStore } from '../stores/codex-store'
import { THEME_OPTIONS, useUIStore } from '../stores/ui-store'
import styles from './Layout.module.css'

const BREADCRUMB_CHAT_PATHS = [
  '/projects/:projectId/nodes/:nodeId/chat',
  '/projects/:projectId/nodes/:nodeId/chat-v2',
]

export function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const theme = useUIStore((state) => state.theme)
  const setTheme = useUIStore((state) => state.setTheme)
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)
  const initializeCodex = useCodexStore((state) => state.initialize)
  const disconnectCodex = useCodexStore((state) => state.disconnect)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'default') {
      root.removeAttribute('data-theme')
    } else {
      root.setAttribute('data-theme', theme)
    }
  }, [theme])

  const [appVersion, setAppVersion] = useState('v1')

  useEffect(() => {
    void initializeCodex()
    return () => {
      disconnectCodex()
    }
  }, [disconnectCodex, initializeCodex])

  useEffect(() => {
    if (window.electronAPI?.getAppVersion) {
      window.electronAPI.getAppVersion().then((v) => setAppVersion(`v${v}`))
    }
  }, [])

  const showBackToGraph = BREADCRUMB_CHAT_PATHS.some(
    (path) => matchPath(path, location.pathname) != null,
  )

  function handleBackToGraph() {
    setActiveSurface('graph')
    navigate('/')
  }

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <div className={styles.topbarLeft}>
          {showBackToGraph ? (
            <button
              type="button"
              className={styles.headerBackButton}
              onClick={handleBackToGraph}
              aria-label="Back to Graph"
            >
              <svg className={styles.headerBackIcon} viewBox="0 0 16 16" fill="none" aria-hidden>
                <path
                  d="M6.5 3.5 2 8m0 0 4.5 4.5M2 8h12"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          ) : null}
          <h1 className={styles.brand}>
            <span className={styles.brandDot} aria-hidden="true" />
            <span className={styles.brandName}>PlanningTree</span>
            <span className={styles.brandSub}>{appVersion}</span>
          </h1>
        </div>
        <div className={styles.inlineActions}>
          <div className={styles.themeSwitcher} title="Switch theme">
            {THEME_OPTIONS.map((themeOption) => (
              <button
                key={themeOption.id}
                type="button"
                className={`${styles.themeSwatch} ${theme === themeOption.id ? styles.active : ''}`}
                aria-label={themeOption.label}
                title={themeOption.label}
                style={{ backgroundColor: themeOption.swatch, color: themeOption.swatch }}
                onClick={() => setTheme(themeOption.id)}
              />
            ))}
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
