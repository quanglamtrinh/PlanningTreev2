import { useEffect, useState } from 'react'
import styles from './App.module.css'

// Scaffold shell — replaced in Phase 3 with React Router + feature workspaces

type BackendStatus = 'connecting' | 'connected' | 'error'

export default function App() {
  const [status, setStatus] = useState<BackendStatus>('connecting')

  useEffect(() => {
    fetch('/health')
      .then((r) => {
        if (r.ok) setStatus('connected')
        else setStatus('error')
      })
      .catch(() => setStatus('error'))
  }, [])

  return (
    <div className={styles.shell}>
      <div className={styles.card}>
        <h1 className={styles.title}>PlanningTree</h1>
        <p className={styles.subtitle}>Scaffold ready</p>
        <div className={styles.status} data-status={status}>
          <span className={styles.dot} />
          {status === 'connecting' && 'Connecting to backend…'}
          {status === 'connected' && 'Backend connected'}
          {status === 'error' && 'Backend not reachable — start dev server'}
        </div>
      </div>
    </div>
  )
}
