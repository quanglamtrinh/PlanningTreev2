import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useProjectStore } from '../../stores/project-store'
import { SharedMarkdownRenderer } from '../markdown/SharedMarkdownRenderer'
import { Sidebar } from '../graph/Sidebar'
import graphStyles from '../graph/GraphWorkspace.module.css'
import { vscodeMarkdownSyntaxHighlighting } from '../node/codemirror/vscodeMarkdownHighlight'
import styles from './SkillsPage.module.css'

type SkillBlock = {
  id: string
  name: string
  description: string
  repoPath: string
  skillPath: string
  source: 'Global' | 'Form' | 'Manual skill.md'
}

type SkillFormDraft = {
  name: string
  description: string
  repoPath: string
}

const EMPTY_SKILL_FORM: SkillFormDraft = {
  name: '',
  description: '',
  repoPath: '',
}

const MANUAL_SKILL_TEMPLATE = `---
name: ""
description: ""
repo_path: ""
---

# Skill

Describe when to use this skill and how the agent should follow it.
`

const INITIAL_GLOBAL_SKILLS: SkillBlock[] = [
  {
    id: 'structured-output',
    name: 'Structured output',
    description: 'Guidance for returning predictable, parseable responses when a task needs structure.',
    repoPath: '.codex/skills/structured-output',
    skillPath: 'structured-output/SKILL.md',
    source: 'Global',
  },
  {
    id: 'progress-updates',
    name: 'Progress updates',
    description: 'Keeps long-running work visible with concise status updates.',
    repoPath: '.codex/skills/progress-updates',
    skillPath: 'progress-updates/SKILL.md',
    source: 'Global',
  },
  {
    id: 'planning',
    name: 'Planning',
    description: 'Helps break ambiguous work into a clear, reviewable plan before implementation.',
    repoPath: '.codex/skills/planning',
    skillPath: 'planning/SKILL.md',
    source: 'Global',
  },
  {
    id: 'tool-selection',
    name: 'Tool selection',
    description: 'Selects the right local tool for search, file inspection, edits, and validation.',
    repoPath: '.codex/skills/tool-selection',
    skillPath: 'tool-selection/SKILL.md',
    source: 'Global',
  },
]

export function SkillsPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<SkillBlock[]>(INITIAL_GLOBAL_SKILLS)
  const [skillFormDraft, setSkillFormDraft] = useState<SkillFormDraft>(EMPTY_SKILL_FORM)
  const [addMode, setAddMode] = useState<'form' | 'manual'>('form')
  const [manualDraft, setManualDraft] = useState(MANUAL_SKILL_TEMPLATE)
  const [manualViewMode, setManualViewMode] = useState<'edit' | 'rich'>('edit')
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const { initialize, hasInitialized, isInitializing } = useProjectStore(
    useShallow((s) => ({
      initialize: s.initialize,
      hasInitialized: s.hasInitialized,
      isInitializing: s.isInitializing,
    })),
  )

  useEffect(() => {
    void initialize()
  }, [initialize])

  const canAddFromForm = useMemo(
    () => skillFormDraft.name.trim() !== '' && skillFormDraft.repoPath.trim() !== '',
    [skillFormDraft.name, skillFormDraft.repoPath],
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

  function handleAddSkillFromForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canAddFromForm) {
      return
    }

    const name = skillFormDraft.name.trim()
    const repoPath = skillFormDraft.repoPath.trim()
    setSkills((current) => [
      ...current,
      {
        id: nextSkillId(name, current),
        name,
        description: skillFormDraft.description.trim() || 'No description provided yet.',
        repoPath,
        skillPath: `${trimPath(repoPath)}/SKILL.md`,
        source: 'Form',
      },
    ])
    setSkillFormDraft(EMPTY_SKILL_FORM)
    setStatusMessage(`Added ${name} to this UI session.`)
  }

  function handleAddManualSkill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = parseManualSkill(manualDraft)
    setSkills((current) => [
      ...current,
      {
        id: nextSkillId(parsed.name, current),
        name: parsed.name,
        description: parsed.description,
        repoPath: parsed.repoPath,
        skillPath: `${trimPath(parsed.repoPath)}/SKILL.md`,
        source: 'Manual skill.md',
      },
    ])
    setManualDraft(MANUAL_SKILL_TEMPLATE)
    setManualViewMode('edit')
    setStatusMessage(`Added ${parsed.name} from manual skill.md.`)
  }

  return (
    <section className={graphStyles.view}>
      <Sidebar />
      <div className={`${graphStyles.mainColumn} ${styles.mainColumn}`}>
        <div className={styles.scroll}>
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
            <p className={styles.eyebrow}>Skills</p>
            <h1 className={styles.title}>Global skills registry</h1>
            <p className={styles.subtitle}>
              Browse global skills as reusable blocks, then draft a new skill from a compact form or
              a manual skill.md authoring surface.
            </p>
          </header>

          <section className={styles.registryPanel} aria-labelledby="global-skills-title">
            <div className={styles.panelHeader}>
              <div>
                <h2 id="global-skills-title" className={styles.sectionTitle}>Global skills</h2>
                <p className={styles.sectionDescription}>
                  UI-only registry preview. New entries are added locally until this screen is wired to persistence.
                </p>
              </div>
            </div>

            <div className={styles.registryGrid} aria-label="Global skills">
              {skills.length === 0 ? (
                <p className={styles.emptyState}>No global skills registered yet.</p>
              ) : (
                skills.map((skill) => <SkillRegistryCard key={skill.id} skill={skill} />)
              )}
            </div>
          </section>

          <section className={styles.addPanel} aria-labelledby="add-skill-title">
            <div className={styles.panelHeader}>
              <div>
                <h2 id="add-skill-title" className={styles.sectionTitle}>Add skill</h2>
                <p className={styles.sectionDescription}>
                  Choose the quick form or draft a full skill.md with the same Rich View used by frame.md and spec.md.
                </p>
              </div>
            </div>

            {statusMessage ? <div className={styles.statusBanner}>{statusMessage}</div> : null}

            <div className={styles.modeTabs} role="tablist" aria-label="Add skill method">
              <button
                type="button"
                className={`${styles.modeTab} ${addMode === 'form' ? styles.modeTabActive : ''}`}
                role="tab"
                aria-selected={addMode === 'form'}
                onClick={() => setAddMode('form')}
              >
                Form
              </button>
              <button
                type="button"
                className={`${styles.modeTab} ${addMode === 'manual' ? styles.modeTabActive : ''}`}
                role="tab"
                aria-selected={addMode === 'manual'}
                onClick={() => setAddMode('manual')}
              >
                Manual skill.md
              </button>
            </div>

            {addMode === 'form' ? (
              <form className={styles.skillForm} onSubmit={handleAddSkillFromForm}>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Skill name</span>
                  <input
                    className={styles.input}
                    value={skillFormDraft.name}
                    onChange={(event) => setSkillFormDraft((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Browser automation"
                  />
                </label>
                <label className={`${styles.field} ${styles.fieldWide}`}>
                  <span className={styles.fieldLabel}>Description</span>
                  <input
                    className={styles.input}
                    value={skillFormDraft.description}
                    onChange={(event) => setSkillFormDraft((current) => ({ ...current, description: event.target.value }))}
                    placeholder="Use when a task requires persistent browser interaction."
                  />
                </label>
                <label className={`${styles.field} ${styles.fieldWide}`}>
                  <span className={styles.fieldLabel}>Repo path</span>
                  <input
                    className={styles.input}
                    value={skillFormDraft.repoPath}
                    onChange={(event) => setSkillFormDraft((current) => ({ ...current, repoPath: event.target.value }))}
                    placeholder=".codex/skills/browser-automation"
                  />
                </label>
                <div className={styles.formActions}>
                  <button type="submit" className={styles.primaryButton} disabled={!canAddFromForm}>
                    Add skill
                  </button>
                </div>
              </form>
            ) : (
              <form className={styles.manualForm} onSubmit={handleAddManualSkill}>
                <div className={styles.editorShell}>
                  <div className={styles.editorHeader}>
                    <span className={styles.editorTitle}>skill.md</span>
                    <div className={styles.editorModeToggle} role="group" aria-label="Manual skill view mode">
                      <button
                        type="button"
                        className={`${styles.editorModeToggleButton} ${manualViewMode === 'edit' ? styles.editorModeToggleButtonActive : ''}`}
                        aria-pressed={manualViewMode === 'edit'}
                        onClick={() => setManualViewMode('edit')}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className={`${styles.editorModeToggleButton} ${manualViewMode === 'rich' ? styles.editorModeToggleButtonActive : ''}`}
                        aria-pressed={manualViewMode === 'rich'}
                        onClick={() => setManualViewMode('rich')}
                      >
                        Rich View
                      </button>
                    </div>
                  </div>
                  <div className={styles.editorBody}>
                    {manualViewMode === 'rich' ? (
                      <div className={styles.richViewSurface} data-testid="manual-skill-rich-view">
                        {manualDraft.trim() ? (
                          <SharedMarkdownRenderer content={manualDraft} variant="document" />
                        ) : (
                          <p className={styles.richViewEmpty}>No content yet.</p>
                        )}
                      </div>
                    ) : (
                      <CodeMirror
                        className={styles.markdownEditor}
                        value={manualDraft}
                        height="100%"
                        theme="none"
                        extensions={[markdown(), vscodeMarkdownSyntaxHighlighting, EditorView.lineWrapping]}
                        basicSetup={{
                          foldGutter: false,
                          lineNumbers: true,
                        }}
                        onChange={setManualDraft}
                      />
                    )}
                  </div>
                </div>
                <div className={styles.formActions}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() => {
                      setManualDraft(MANUAL_SKILL_TEMPLATE)
                      setManualViewMode('edit')
                    }}
                  >
                    Reset template
                  </button>
                  <button type="submit" className={styles.primaryButton}>
                    Add manual skill
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      </div>
    </section>
  )
}

function SkillRegistryCard({ skill }: { skill: SkillBlock }) {
  return (
    <article className={styles.skillCard}>
      <div className={styles.cardHeader}>
        <div>
          <h3 className={styles.cardTitle}>{skill.name}</h3>
          <p className={styles.description}>{skill.description}</p>
        </div>
        <span className={styles.badge}>{skill.source}</span>
      </div>
      <code className={styles.skillPath}>{skill.skillPath}</code>
      <div className={styles.skillMeta}>
        <span>Repo path</span>
        <code>{skill.repoPath}</code>
      </div>
    </article>
  )
}

function trimPath(path: string): string {
  return path.trim().replace(/[\\/]+$/, '')
}

function nextSkillId(name: string, existing: SkillBlock[]): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'skill'
  const existingIds = new Set(existing.map((skill) => skill.id))
  if (!existingIds.has(base)) {
    return base
  }
  let suffix = 2
  while (existingIds.has(`${base}-${suffix}`)) {
    suffix += 1
  }
  return `${base}-${suffix}`
}

function parseManualSkill(content: string): Pick<SkillBlock, 'name' | 'description' | 'repoPath'> {
  const frontmatter = parseFrontmatter(content)
  const fallbackName = firstMarkdownHeading(content) ?? 'Manual skill'
  const name = frontmatter.name || fallbackName
  return {
    name,
    description: frontmatter.description || 'Manual skill.md draft.',
    repoPath: frontmatter.repo_path || `.codex/skills/${nextSlug(name)}`,
  }
}

function parseFrontmatter(content: string): Record<string, string> {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---/)
  if (!match) {
    return {}
  }

  return match[1].split('\n').reduce<Record<string, string>>((fields, line) => {
    const separatorIndex = line.indexOf(':')
    if (separatorIndex === -1) {
      return fields
    }
    const key = line.slice(0, separatorIndex).trim()
    const value = line.slice(separatorIndex + 1).trim().replace(/^['"]|['"]$/g, '')
    if (key && value) {
      fields[key] = value
    }
    return fields
  }, {})
}

function firstMarkdownHeading(content: string): string | null {
  const heading = content.split('\n').find((line) => line.startsWith('# '))
  return heading ? heading.replace(/^#\s+/, '').trim() : null
}

function nextSlug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'manual-skill'
}
