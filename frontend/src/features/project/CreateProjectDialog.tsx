import { FormEvent, useState } from 'react'
import styles from './CreateProjectDialog.module.css'

type Props = {
  isSubmitting: boolean
  compact?: boolean
  onCreate: (name: string, rootGoal: string) => Promise<void>
}

export function CreateProjectDialog({
  isSubmitting,
  compact = false,
  onCreate,
}: Props) {
  const [name, setName] = useState('')
  const [rootGoal, setRootGoal] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onCreate(name, rootGoal)
    setName('')
    setRootGoal('')
  }

  return (
    <form className={`${styles.card} ${compact ? styles.compact : ''}`} onSubmit={handleSubmit}>
      {!compact && (
        <div className={styles.header}>
          <p className={styles.kicker}>New Project</p>
          <p className={styles.subtitle}>Create a planning tree from a root goal.</p>
        </div>
      )}
      <label className={styles.field}>
        {!compact && <span>Name</span>}
        <input
          value={name}
          placeholder={compact ? 'Project name' : ''}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className={styles.field}>
        {!compact && <span>Root goal</span>}
        <textarea
          rows={compact ? 1 : 3}
          value={rootGoal}
          placeholder={compact ? 'Root goal' : ''}
          onChange={(event) => setRootGoal(event.target.value)}
        />
      </label>
      <button className={styles.primary} type="submit" disabled={isSubmitting}>
        {isSubmitting ? '…' : compact ? '+ New' : 'Create Project'}
      </button>
    </form>
  )
}
