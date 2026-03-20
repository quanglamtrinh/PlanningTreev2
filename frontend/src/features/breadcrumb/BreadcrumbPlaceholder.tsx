import { useEffect } from 'react'
import { useUIStore } from '../../stores/ui-store'
import styles from './BreadcrumbPlaceholder.module.css'

export function BreadcrumbPlaceholder() {
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  useEffect(() => {
    setActiveSurface('breadcrumb')
  }, [setActiveSurface])

  return (
    <section className={styles.view}>
      <div className={styles.card}>
        <p className={styles.eyebrow}>Rework in progress</p>
        <h1>Breadcrumb view is being reworked.</h1>
        <p>
          This route is intentionally kept alive as a temporary placeholder while
          the old breadcrumb workspace is retired.
        </p>
      </div>
    </section>
  )
}
