import { useEffect, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useProjectStore } from '../../stores/project-store'
import { Sidebar } from '../graph/Sidebar'
import graphStyles from '../graph/GraphWorkspace.module.css'
import styles from './ExtensionsPage.module.css'

type GlobalExtension = {
  id: string
  name: string
  description: string
  badge: string
}

type McpServerDraft = {
  name: string
  transport: 'stdio' | 'sse' | 'http'
  target: string
  env: string
}

type McpServer = McpServerDraft & {
  id: string
}

const EMPTY_MCP_SERVER_DRAFT: McpServerDraft = {
  name: '',
  transport: 'stdio',
  target: '',
  env: '',
}

const AVAILABLE_GLOBAL_EXTENSIONS: readonly GlobalExtension[] = [
  {
    id: 'context-sync',
    name: 'Context Sync',
    description: 'Keeps node context, docs, and latest workspace notes aligned before execution.',
    badge: 'Workspace',
  },
  {
    id: 'risk-scan',
    name: 'Risk Scan',
    description: 'Highlights dependency, migration, and rollout risks while planning a task.',
    badge: 'Review',
  },
  {
    id: 'handoff-pack',
    name: 'Handoff Pack',
    description: 'Drafts a compact handoff with open questions, changed files, and next actions.',
    badge: 'Docs',
  },
  {
    id: 'spec-guard',
    name: 'Spec Guard',
    description: 'Checks whether a task still matches the current acceptance criteria and scope.',
    badge: 'Planning',
  },
  {
    id: 'test-weaver',
    name: 'Test Weaver',
    description: 'Suggests focused unit and integration test coverage for high-risk changes.',
    badge: 'Quality',
  },
  {
    id: 'dependency-watch',
    name: 'Dependency Watch',
    description: 'Surfaces package, API, and lockfile impacts before implementation begins.',
    badge: 'Build',
  },
  {
    id: 'release-notes',
    name: 'Release Notes',
    description: 'Collects user-facing changes into a concise draft for release communication.',
    badge: 'Release',
  },
  {
    id: 'accessibility-pass',
    name: 'Accessibility Pass',
    description: 'Reviews interactive UI states, labels, keyboard paths, and contrast concerns.',
    badge: 'UX',
  },
  {
    id: 'perf-pulse',
    name: 'Perf Pulse',
    description: 'Flags potentially expensive render paths, data fetching, and bundle growth.',
    badge: 'Performance',
  },
  {
    id: 'migration-guide',
    name: 'Migration Guide',
    description: 'Prepares data, config, and rollout notes for changes that alter persisted behavior.',
    badge: 'Ops',
  },
] as const

export function ExtensionsPage() {
  const [mcpServerDraft, setMcpServerDraft] = useState<McpServerDraft>(EMPTY_MCP_SERVER_DRAFT)
  const [mcpServers, setMcpServers] = useState<McpServer[]>([])
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

  const canAddMcpServer = mcpServerDraft.name.trim() !== '' && mcpServerDraft.target.trim() !== ''

  function handleAddMcpServer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canAddMcpServer) return
    const normalizedName = mcpServerDraft.name.trim()
    setMcpServers((current) => [
      ...current,
      {
        ...mcpServerDraft,
        id: `${normalizedName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${Date.now()}`,
        name: normalizedName,
        target: mcpServerDraft.target.trim(),
        env: mcpServerDraft.env.trim(),
      },
    ])
    setMcpServerDraft(EMPTY_MCP_SERVER_DRAFT)
  }

  return (
    <section className={graphStyles.view}>
      <Sidebar />
      <div className={`${graphStyles.mainColumn} ${styles.mainColumn}`}>
        <div className={styles.scroll}>
          <header className={styles.hero}>
            <p className={styles.eyebrow}>Extensions</p>
            <h1 className={styles.title}>Available global extensions</h1>
            <p className={styles.subtitle}>
              Browse dummy global extensions that can later be wired into project and node workflows.
            </p>
          </header>

          <section className={styles.mcpPanel} aria-labelledby="mcp-server-form-title">
            <div className={styles.mcpPanelHeader}>
              <div>
                <h2 id="mcp-server-form-title" className={styles.sectionTitle}>Add MCP server</h2>
                <p className={styles.sectionDescription}>
                  Register a local mock server entry. This UI is ready for backend wiring later.
                </p>
              </div>
            </div>

            <form className={styles.mcpForm} onSubmit={handleAddMcpServer}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Server name</span>
                <input
                  className={styles.input}
                  value={mcpServerDraft.name}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Linear MCP"
                />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Transport</span>
                <select
                  className={styles.input}
                  value={mcpServerDraft.transport}
                  onChange={(event) =>
                    setMcpServerDraft((current) => ({
                      ...current,
                      transport: event.target.value as McpServerDraft['transport'],
                    }))
                  }
                >
                  <option value="stdio">stdio</option>
                  <option value="sse">sse</option>
                  <option value="http">http</option>
                </select>
              </label>

              <label className={`${styles.field} ${styles.fieldWide}`}>
                <span className={styles.fieldLabel}>Command or URL</span>
                <input
                  className={styles.input}
                  value={mcpServerDraft.target}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, target: event.target.value }))}
                  placeholder="npx -y @modelcontextprotocol/server-filesystem ."
                />
              </label>

              <label className={`${styles.field} ${styles.fieldWide}`}>
                <span className={styles.fieldLabel}>Environment notes</span>
                <textarea
                  className={`${styles.input} ${styles.textarea}`}
                  value={mcpServerDraft.env}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, env: event.target.value }))}
                  placeholder="API_KEY=... or auth setup notes"
                  rows={3}
                />
              </label>

              <div className={styles.formActions}>
                <button type="submit" className={styles.primaryButton} disabled={!canAddMcpServer}>
                  Add server
                </button>
              </div>
            </form>

            <div className={styles.mcpServerList} aria-label="Added MCP servers">
              {mcpServers.length === 0 ? (
                <p className={styles.emptyMcpState}>No MCP servers added yet.</p>
              ) : (
                mcpServers.map((server) => (
                  <article key={server.id} className={styles.mcpServerCard}>
                    <div className={styles.cardHeader}>
                      <h3 className={styles.cardTitle}>{server.name}</h3>
                      <span className={styles.badge}>{server.transport}</span>
                    </div>
                    <code className={styles.serverTarget}>{server.target}</code>
                    {server.env ? <p className={styles.description}>{server.env}</p> : null}
                  </article>
                ))
              )}
            </div>
          </section>

          <section className={styles.grid} aria-label="Available global extensions">
            {AVAILABLE_GLOBAL_EXTENSIONS.map((extension) => (
              <article key={extension.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <h2 className={styles.cardTitle}>{extension.name}</h2>
                  <span className={styles.badge}>{extension.badge}</span>
                </div>
                <p className={styles.description}>{extension.description}</p>
              </article>
            ))}
          </section>
        </div>
      </div>
    </section>
  )
}

