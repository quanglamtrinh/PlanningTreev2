import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useUIStore } from '../../stores/ui-store'
import { BreadcrumbChatView } from './BreadcrumbChatView'
import styles from './BreadcrumbPlaceholder.module.css'

export function BreadcrumbPlaceholder() {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
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
      <div className={styles.toolbar}>
        <button type="button" className={styles.backButton} onClick={handleBackToGraph}>
          <svg
            className={styles.backIcon}
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M6.5 3.5 2 8m0 0 4.5 4.5M2 8h12"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Back to graph</span>
        </button>

        <div className={styles.context}>
          <p className={styles.eyebrow}>Breadcrumb view</p>
          <p className={styles.meta}>
            {projectId ? `Project ${projectId}` : 'Project'}
            {nodeId ? ` / Node ${nodeId}` : ''}
          </p>
        </div>
      </div>

      <div className={styles.chatPanel}>
        <BreadcrumbChatView />
      </div>
    </section>
  )
}
