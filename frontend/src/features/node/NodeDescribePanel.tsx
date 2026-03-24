import type { ChangedFileRecord, DetailState, NodeRecord } from '../../api/types'
import styles from './NodeDetailCard.module.css'

type Props = {
  node: NodeRecord
  projectId: string
  detailState?: DetailState | null
  onResetToBefore?: () => void | Promise<void>
  onResetToResult?: () => void | Promise<void>
  isResetting?: boolean
}

function displaySha(value: string | null | undefined): string {
  if (value == null || String(value).trim() === '') return '—'
  return String(value).trim()
}

function normalizeChangedFiles(raw: DetailState['changed_files']): ChangedFileRecord[] {
  if (!raw || !Array.isArray(raw)) return []
  return raw.map((item): ChangedFileRecord => {
    if (typeof item === 'string') {
      return { path: item, status: 'M' }
    }
    const status = item.status ?? 'M'
    const path = item.path ?? ''
    return {
      path,
      status: status === 'A' || status === 'M' || status === 'D' || status === 'R' ? status : 'M',
      previous_path: item.previous_path,
    }
  })
}

function statusLabel(status: ChangedFileRecord['status']): string {
  switch (status) {
    case 'A':
      return 'Added'
    case 'M':
      return 'Modified'
    case 'D':
      return 'Deleted'
    case 'R':
      return 'Renamed'
    default:
      return status
  }
}

export function NodeDescribePanel({
  node,
  projectId,
  detailState,
  onResetToBefore,
  onResetToResult,
  isResetting = false,
}: Props) {
  void projectId
  const initialSha = displaySha(detailState?.initial_sha)
  const headSha = displaySha(detailState?.head_sha)
  const currentHead = displaySha(detailState?.current_head_sha)
  const commitMessage = detailState?.commit_message?.trim()
    ? detailState.commit_message
    : '—'
  const changedFiles = normalizeChangedFiles(detailState?.changed_files)

  const present = detailState?.task_present_in_current_workspace
  const taskMissing = present === false
  const canReset =
    !taskMissing &&
    Boolean(detailState?.initial_sha?.trim()) &&
    Boolean(detailState?.head_sha?.trim())

  return (
    <div className={styles.describePanel}>
      <div className={styles.contentPanel}>
        <p className={styles.eyebrow}>
          {node.hierarchical_number ? `${node.hierarchical_number} - Node` : 'Node'}
        </p>
        <h3 className={styles.title}>{node.title}</h3>
        <p className={styles.body}>{node.description.trim() || 'No description yet.'}</p>
        <p className={styles.body}>
          Status: <strong>{node.status}</strong> . Children: {node.child_ids.length}
        </p>
      </div>

      {taskMissing ? (
        <div className={styles.describeTaskMissingBanner} role="note">
          This task&apos;s checkpoint commits are not on the current branch history. You may have
          moved the workspace with a hard reset. Reset actions are disabled until the repo state
          matches a known checkpoint.
        </div>
      ) : null}

      <div className={styles.describeCommitSection}>
        <h4 className={styles.describeSectionTitle}>Commit</h4>
        <div className={styles.shaFieldRow}>
          <label className={styles.shaFieldLabel} htmlFor="describe-initial-sha">
            Initial SHA
          </label>
          <input
            id="describe-initial-sha"
            className={styles.shaFieldInput}
            readOnly
            value={initialSha}
            aria-label="Initial SHA"
          />
        </div>
        <div className={styles.shaFieldRow}>
          <label className={styles.shaFieldLabel} htmlFor="describe-head-sha">
            Head SHA
          </label>
          <input
            id="describe-head-sha"
            className={styles.shaFieldInput}
            readOnly
            value={headSha}
            aria-label="Head SHA"
          />
        </div>
        <div className={styles.shaFieldRow}>
          <label className={styles.shaFieldLabel} htmlFor="describe-current-head">
            Current HEAD
          </label>
          <input
            id="describe-current-head"
            className={styles.shaFieldInput}
            readOnly
            value={currentHead}
            aria-label="Current repository HEAD"
          />
        </div>
        <div className={styles.shaFieldRow}>
          <label className={styles.shaFieldLabel} htmlFor="describe-commit-msg">
            Commit message
          </label>
          <input
            id="describe-commit-msg"
            className={styles.shaFieldInput}
            readOnly
            value={commitMessage ?? '—'}
            aria-label="Commit message for this task"
          />
        </div>
      </div>

      <div className={styles.describeFilesSection}>
        <h4 className={styles.describeSectionTitle}>Changed files</h4>
        {changedFiles.length === 0 ? (
          <p className={styles.changedFilesEmpty}>No changed files recorded for this task.</p>
        ) : (
          <ul className={styles.changedFilesList}>
            {changedFiles.map((file) => {
              const key = `${file.status}:${file.previous_path ?? ''}:${file.path}`
              return (
                <li key={key} className={styles.changedFilesItem}>
                  <span
                    className={styles.changedFilesStatus}
                    data-status={file.status}
                    title={statusLabel(file.status)}
                  >
                    {file.status}
                  </span>
                  <code className={styles.changedFilesPath}>
                    {file.status === 'R' && file.previous_path
                      ? `${file.previous_path} → ${file.path}`
                      : file.path}
                  </code>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className={styles.describeWorkspaceSection}>
        <h4 className={styles.describeSectionTitle}>Workspace</h4>
        <p className={styles.describeWorkspaceHint}>
          Hard reset moves the entire project folder to that checkpoint state. Use only when you
          understand the impact on uncommitted work.
        </p>
        <div className={styles.describeResetRow}>
          <button
            type="button"
            className={styles.resetWorkspaceButtonSecondary}
            disabled={!canReset || isResetting}
            onClick={() => void onResetToBefore?.()}
          >
            {isResetting ? 'Resetting…' : 'Reset to before this task'}
          </button>
          <button
            type="button"
            className={styles.resetWorkspaceButtonDanger}
            disabled={!canReset || isResetting}
            onClick={() => void onResetToResult?.()}
          >
            {isResetting ? 'Resetting…' : 'Reset to this task result'}
          </button>
        </div>
      </div>
    </div>
  )
}
