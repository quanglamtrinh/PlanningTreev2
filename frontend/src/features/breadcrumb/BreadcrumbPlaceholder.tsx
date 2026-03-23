import { useEffect } from 'react'
import { useUIStore } from '../../stores/ui-store'
import { BreadcrumbChatView } from './BreadcrumbChatView'
import styles from './BreadcrumbPlaceholder.module.css'

export function BreadcrumbPlaceholder() {
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  useEffect(() => {
    setActiveSurface('breadcrumb')
  }, [setActiveSurface])

  return (
    <section className={styles.view}>
      <div className={styles.chatPanel}>
        <BreadcrumbChatView />
      </div>
    </section>
  )
}
