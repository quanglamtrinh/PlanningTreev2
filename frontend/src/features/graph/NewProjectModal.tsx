import { FormEvent, useCallback, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import styles from './NewProjectModal.module.css'

type Props = {
  isOpen: boolean
  isSubmitting: boolean
  error: string | null
  baseWorkspaceRoot: string | null
  onClose: () => void
  onSubmit: (name: string, rootGoal: string) => Promise<void>
}

export function NewProjectModal({
  isOpen,
  isSubmitting,
  error,
  baseWorkspaceRoot,
  onClose,
  onSubmit,
}: Props) {
  const [name, setName] = useState('')
  const [rootGoal, setRootGoal] = useState('')
  const nameRef = useRef<HTMLInputElement>(null)

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!name.trim() || !rootGoal.trim()) return
      await onSubmit(name.trim(), rootGoal.trim())
      setName('')
      setRootGoal('')
    },
    [name, rootGoal, onSubmit],
  )

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose()
    },
    [onClose],
  )

  if (!isOpen) return null

  return createPortal(
    <div className={styles.backdrop} onClick={handleBackdropClick}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-label="New project">
        {/* Header */}
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>New Project</h2>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Workspace info */}
        {baseWorkspaceRoot && (
          <div className={styles.workspaceChip}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span className={styles.workspacePath}>{baseWorkspaceRoot}</span>
          </div>
        )}

        {/* Form */}
        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.fieldLabel}>
            Project name
            <input
              ref={nameRef}
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. MyFeature"
              autoFocus
              autoComplete="off"
              required
            />
          </label>

          <label className={styles.fieldLabel}>
            Root goal
            <textarea
              className={styles.textarea}
              value={rootGoal}
              onChange={(e) => setRootGoal(e.target.value)}
              placeholder="Describe the high-level goal for this project…"
              rows={3}
              required
            />
          </label>

          {error && <p className={styles.errorMsg}>{error}</p>}

          <div className={styles.formActions}>
            <button type="button" className={styles.cancelBtn} onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={styles.submitBtn}
              disabled={isSubmitting || !name.trim() || !rootGoal.trim()}
            >
              {isSubmitting ? 'Creating…' : 'Create project'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  )
}
