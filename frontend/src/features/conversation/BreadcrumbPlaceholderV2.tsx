import { useEffect } from 'react'
import { useUIStore } from '../../stores/ui-store'
import styles from '../breadcrumb/BreadcrumbPlaceholder.module.css'
import { BreadcrumbChatViewV2 } from './BreadcrumbChatViewV2'

export function BreadcrumbPlaceholderV2() {
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  useEffect(() => {
    setActiveSurface('breadcrumb')
  }, [setActiveSurface])

  return (
    <section className={styles.view}>
      <div className={styles.chatPanel}>
        <BreadcrumbChatViewV2 />
      </div>
    </section>
  )
}
