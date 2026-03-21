import { Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { useCodexStore } from '../stores/codex-store'
import { THEME_OPTIONS, useUIStore } from '../stores/ui-store'
import styles from './Layout.module.css'

export function Layout() {
  const theme = useUIStore((state) => state.theme)
  const setTheme = useUIStore((state) => state.setTheme)
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

  useEffect(() => {
    void initializeCodex()
    return () => {
      disconnectCodex()
    }
  }, [disconnectCodex, initializeCodex])

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <h1 className={styles.brand}>
          <span className={styles.brandDot} aria-hidden="true" />
          <span className={styles.brandName}>PlanningTree</span>
          <span className={styles.brandSub}>v1</span>
        </h1>
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
