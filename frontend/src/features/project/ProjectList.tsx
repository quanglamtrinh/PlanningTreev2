import type { ProjectSummary } from '../../api/types'
import styles from './ProjectList.module.css'

type Props = {
  projects: ProjectSummary[]
  activeProjectId: string | null
  isLoading: boolean
  onSelect: (projectId: string | null) => void
  onRefresh: () => void
}

export function ProjectList({
  projects,
  activeProjectId,
  isLoading,
  onSelect,
  onRefresh,
}: Props) {
  return (
    <div className={styles.group}>
      <label className={styles.label}>
        <span className={styles.labelText}>Project</span>
        <select
          className={styles.select}
          value={activeProjectId ?? ''}
          onChange={(event) => onSelect(event.target.value || null)}
        >
          <option value="">Select a project</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className={styles.refreshBtn}
        onClick={onRefresh}
        disabled={isLoading}
      >
        {isLoading ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>
  )
}
