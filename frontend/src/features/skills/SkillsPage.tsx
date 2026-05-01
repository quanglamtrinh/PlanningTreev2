import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { api } from '../../api/client'
import type { SkillMetadata } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { Sidebar } from '../graph/Sidebar'
import graphStyles from '../graph/GraphWorkspace.module.css'
import styles from './SkillsPage.module.css'

function skillDisplayName(skill: SkillMetadata): string {
  return skill.interface?.displayName?.trim() || skill.name
}

function skillDescription(skill: SkillMetadata): string {
  return skill.interface?.shortDescription?.trim() || skill.description || skill.path
}

export function SkillsPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<SkillMetadata[]>([])
  const [catalogCwd, setCatalogCwd] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const { initialize, hasInitialized, isInitializing, activeProjectId } = useProjectStore(
    useShallow((state) => ({
      initialize: state.initialize,
      hasInitialized: state.hasInitialized,
      isInitializing: state.isInitializing,
      activeProjectId: state.activeProjectId,
    })),
  )

  useEffect(() => {
    void initialize()
  }, [initialize])

  useEffect(() => {
    let cancelled = false
    async function loadCatalog() {
      if (!hasInitialized || !activeProjectId) {
        return
      }
      setLoadError(null)
      setSkills([])
      try {
        const response = await api.listSkillsRegistry(activeProjectId)
        if (cancelled) {
          return
        }
        setCatalogCwd(response.catalogCwd)
        setSkills(response.data.flatMap((entry) => entry.skills))
        const errors = response.data.flatMap((entry) => entry.errors ?? [])
        if (errors.length > 0) {
          setLoadError(`${errors.length} skill catalog issue${errors.length === 1 ? '' : 's'} found.`)
        }
      } catch (error) {
        if (cancelled) {
          return
        }
        setLoadError(error instanceof Error ? error.message : 'Failed to load skills catalog')
      }
    }
    void loadCatalog()
    return () => {
      cancelled = true
    }
  }, [activeProjectId, hasInitialized])

  const sortedSkills = useMemo(
    () => [...skills].sort((a, b) => `${a.scope}:${a.name}:${a.path}`.localeCompare(`${b.scope}:${b.name}:${b.path}`)),
    [skills],
  )

  if (!hasInitialized || isInitializing) {
    return (
      <section className={graphStyles.view}>
        <Sidebar />
        <div className={graphStyles.mainColumn}>
          <div className={graphStyles.loading}>Loading...</div>
        </div>
      </section>
    )
  }

  return (
    <section className={graphStyles.view}>
      <Sidebar />
      <div className={`${graphStyles.mainColumn} ${styles.mainColumn}`}>
        <div className={styles.scroll}>
          <div className={styles.pageContent}>
            <header className={styles.hero}>
              <button
                type="button"
                className={styles.backButton}
                onClick={() => navigate('/graph')}
                aria-label="Back to graph"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="m15 18-6-6 6-6" />
                </svg>
                Back
              </button>
              <div className={styles.titleGroup}>
                <p className={styles.eyebrow}>Skills</p>
                <h1 className={styles.title}>Global skills registry</h1>
              </div>
              <p className={styles.subtitle}>
                Browse Codex-discovered skills for the active project. Thread roles choose from this catalog in each node&apos;s Info tab.
              </p>
            </header>

            <section className={styles.registryPanel} aria-labelledby="global-skills-title">
              <div className={styles.panelHeader}>
                <div>
                  <h2 id="global-skills-title" className={styles.sectionTitle}>Global skills</h2>
                  <p className={styles.sectionDescription}>
                    {catalogCwd ? `Catalog cwd: ${catalogCwd}` : 'Select a project to load its Codex skills catalog.'}
                  </p>
                </div>
              </div>

              {loadError ? <p className={styles.emptyState}>{loadError}</p> : null}
              <div className={styles.registryGrid} aria-label="Global skills">
                {sortedSkills.length === 0 ? (
                  <p className={styles.emptyState}>No Codex skills found for this project.</p>
                ) : (
                  sortedSkills.map((skill) => <SkillRegistryCard key={skill.path} skill={skill} />)
                )}
              </div>
            </section>

            <section className={styles.addPanel} aria-labelledby="add-skill-title">
              <div className={styles.panelHeader}>
                <div>
                  <h2 id="add-skill-title" className={styles.sectionTitle}>Authoring</h2>
                  <p className={styles.sectionDescription}>
                    Skill authoring is deferred until this screen writes real `.codex/skills/&lt;name&gt;/SKILL.md` files. Use the workspace file tools for now.
                  </p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </section>
  )
}

function SkillRegistryCard({ skill }: { skill: SkillMetadata }) {
  const dependencyCount = skill.dependencies?.tools?.length ?? 0
  return (
    <article className={styles.skillCard}>
      <div className={styles.skillCardHeader}>
        <div>
          <h3 className={styles.skillName}>{skillDisplayName(skill)}</h3>
          <p className={styles.skillDescription}>{skillDescription(skill)}</p>
        </div>
        <span className={styles.sourceBadge}>{skill.scope}</span>
      </div>
      <dl className={styles.skillMetaList}>
        <div>
          <dt>Skill path</dt>
          <dd>{skill.path}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{skill.enabled ? 'Enabled' : 'Disabled by Codex config'}</dd>
        </div>
        <div>
          <dt>Dependencies</dt>
          <dd>{dependencyCount === 0 ? 'None declared' : `${dependencyCount} tool${dependencyCount === 1 ? '' : 's'}`}</dd>
        </div>
      </dl>
    </article>
  )
}
