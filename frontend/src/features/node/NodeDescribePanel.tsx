import type { ChangedFileRecord, DetailState, NodeRecord } from '../../api/types'
import styles from './NodeDetailCard.module.css'

const INFO_TAB_SKILLS_PATHS = [
  'structured-output/SKILL.md',
  'progress-updates/SKILL.md',
  'planning/SKILL.md',
  'tool-selection/SKILL.md',
] as const

const INFO_TAB_DOCS_PATHS = [
  'docs/codebase-summary.md',
  'docs/project-roadmap.md',
  'workflows/handoff',
  'workflows/development-rules.md',
] as const

function IconInfoDoc() {
  return (
    <svg className={styles.infoPathIconSvg} viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path fill="currentColor" d="M4 1.75h6.93l3.82 3.82V15.25H4.75V1.75H4z" />
      <path
        fill="currentColor"
        fillOpacity="0.38"
        d="M10.93 1.75 14.75 5.57h-3.82V1.75z"
      />
      <rect x="5.1" y="8.05" width="7.8" height="1.1" rx="0.3" fill="#fff" fillOpacity="0.9" />
      <rect x="5.1" y="10.25" width="7.8" height="1.1" rx="0.3" fill="#fff" fillOpacity="0.9" />
      <rect x="5.1" y="12.45" width="4.9" height="1.1" rx="0.3" fill="#fff" fillOpacity="0.9" />
    </svg>
  )
}

function IconInfoSkill() {
  return (
    <svg className={styles.infoPathIconSvg} viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path
        fill="currentColor"
        d="m9 1.8 1.05 2.7 2.88.4-2.2 1.9.68 2.8L9 8.55 5.59 9.6l.68-2.8-2.2-1.9 2.88-.4L9 1.8Z"
      />
      <path
        fill="currentColor"
        fillOpacity="0.55"
        d="m14.2 10.35.55 1.42 1.52.2-1.15 1 .35 1.48-1.27-.72-1.27.72.35-1.48-1.15-1 1.52-.2.55-1.42Z"
      />
      <path
        fill="currentColor"
        fillOpacity="0.45"
        d="m3.35 11.5.45 1.15 1.22.18-.92.78.28 1.2-1.03-.58-1.03.58.28-1.2-.92-.78 1.22-.18.45-1.15Z"
      />
    </svg>
  )
}

function InfoPathList({
  paths,
  variant,
  'data-testid': testId,
}: {
  paths: readonly string[]
  variant: 'docs' | 'skills'
  'data-testid'?: string
}) {
  return (
    <ul className={styles.infoPathList} data-testid={testId}>
      {paths.map((path) => (
        <li key={path} className={styles.infoPathItem}>
          <span
            className={variant === 'docs' ? styles.infoPathIconDoc : styles.infoPathIconSkill}
            aria-hidden
          >
            {variant === 'docs' ? <IconInfoDoc /> : <IconInfoSkill />}
          </span>
          <code className={styles.infoPathCode}>{path}</code>
          <span className={styles.infoPathChevron} aria-hidden>
            <svg viewBox="0 0 8 14" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M1.5 1.5 6.5 7l-5 5.5"
                stroke="currentColor"
                strokeWidth="1.35"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </li>
      ))}
    </ul>
  )
}

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
    detailState?.execution_started === true &&
    Boolean(detailState?.initial_sha?.trim()) &&
    Boolean(detailState?.head_sha?.trim())

  return (
    <div className={styles.describeDocumentRoot}>
      <div className={styles.describeDocumentSheet}>
        <div className={styles.describePanel}>
          <div className={styles.describeDocHero}>
            <p className={styles.eyebrow}>
              {node.hierarchical_number ? `${node.hierarchical_number} - Node` : 'Node'}
            </p>
            <h1 className={styles.describeDocH1}>{node.title}</h1>
            <p className={styles.body}>{node.description.trim() || 'No description yet.'}</p>
            <p className={styles.body}>
              Status: <strong>{node.status}</strong> · Children: {node.child_ids.length}
            </p>
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeDocsSection}>
              <h2 className={styles.describeSectionTitle}>Docs</h2>
              <InfoPathList variant="docs" paths={INFO_TAB_DOCS_PATHS} data-testid="info-tab-docs-paths" />
            </div>
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeSystemPromptsSection}>
              <h2 className={styles.describeSectionTitle}>System prompts</h2>
              <p className={styles.changedFilesEmpty}>No system prompts attached.</p>
            </div>
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeSkillsSection}>
              <h2 className={styles.describeSectionTitle}>Skills</h2>
              <InfoPathList variant="skills" paths={INFO_TAB_SKILLS_PATHS} data-testid="info-tab-skills-paths" />
            </div>
          </div>

          {taskMissing ? (
            <div className={styles.describeDocSection}>
              <div className={styles.describeTaskMissingBanner} role="note">
                This task&apos;s checkpoint commits are not on the current branch history. You may
                have moved the workspace with a hard reset. Reset actions are disabled until the repo
                state matches a known checkpoint.
              </div>
            </div>
          ) : null}

          <div className={styles.describeDocSection}>
            <div className={styles.describeCommitSection}>
              <h2 className={styles.describeSectionTitle}>Commit</h2>
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
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeFilesSection}>
              <h2 className={styles.describeSectionTitle}>Changed files</h2>
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
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeWorkspaceSection}>
              <h2 className={styles.describeSectionTitle}>Workspace</h2>
              <p className={styles.describeWorkspaceHint}>
                Hard reset moves the entire project folder to that checkpoint state. Use only when
                you understand the impact on uncommitted work.
              </p>
              <div className={styles.describeWorkspaceActions}>
                <button
                  type="button"
                  className={styles.describeWorkspaceButtonOutline}
                  disabled={!canReset || isResetting}
                  onClick={() => void onResetToBefore?.()}
                >
                  {isResetting ? 'Resetting…' : 'Reset to before this task'}
                </button>
                <button
                  type="button"
                  className={styles.describeWorkspaceButtonPrimary}
                  disabled={!canReset || isResetting}
                  onClick={() => void onResetToResult?.()}
                >
                  {isResetting ? 'Resetting…' : 'Reset to this task result'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
