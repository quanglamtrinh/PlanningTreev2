import { FormEvent, useEffect, useState } from 'react'
import styles from './WorkspaceSetup.module.css'

type Props = {
  initialValue?: string | null
  isSaving: boolean
  error: string | null
  compact?: boolean
  onSubmit: (path: string) => Promise<void>
  onCancel?: () => void
}

export function WorkspaceSetup({
  initialValue = '',
  isSaving,
  error,
  compact = false,
  onSubmit,
  onCancel,
}: Props) {
  const [path, setPath] = useState(initialValue ?? '')

  useEffect(() => {
    setPath(initialValue ?? '')
  }, [initialValue])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit(path)
  }

  return (
    <section className={`${styles.shell} ${compact ? styles.compact : ''}`}>
      <div className={styles.card}>
        <p className={styles.kicker}>Workspace Setup</p>
        <h2 className={styles.title}>Choose a base workspace folder</h2>
        <p className={styles.subtitle}>
          PlanningTree creates each project inside this base directory. The folder must
          already exist and be writable.
        </p>
        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.label}>
            Base workspace root
            <input
              className={styles.input}
              value={path}
              onChange={(event) => setPath(event.target.value)}
              placeholder="C:\Projects"
              autoComplete="off"
            />
          </label>
          {error ? <p className={styles.error}>{error}</p> : null}
          <div className={styles.actions}>
            <button className={styles.primary} type="submit" disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Workspace'}
            </button>
            {onCancel ? (
              <button type="button" onClick={onCancel}>
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      </div>
    </section>
  )
}
