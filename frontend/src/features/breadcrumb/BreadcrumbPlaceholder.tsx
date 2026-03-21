import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUIStore } from '../../stores/ui-store'
import { BreadcrumbChatView } from './BreadcrumbChatView'
import styles from './BreadcrumbPlaceholder.module.css'

export function BreadcrumbPlaceholder() {
  const navigate = useNavigate()
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  useEffect(() => {
    setActiveSurface('breadcrumb')
  }, [setActiveSurface])

  function handleBackToGraph() {
    setActiveSurface('graph')
    navigate('/')
  }

  return (
    <section className={styles.view}>
      <button
        type="button"
        className={styles.backButton}
        onClick={handleBackToGraph}
        aria-label="Back to Graph"
      >
        <svg className={styles.backIcon} viewBox="0 0 16 16" fill="none" aria-hidden>
          <path
            d="M6.5 3.5 2 8m0 0 4.5 4.5M2 8h12"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      <div className={styles.chatPanel}>
        <BreadcrumbChatView />
      </div>
    </section>
  )
}
