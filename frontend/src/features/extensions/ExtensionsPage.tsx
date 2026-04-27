import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { api } from '../../api/client'
import type { McpRegistryServer } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { Sidebar } from '../graph/Sidebar'
import graphStyles from '../graph/GraphWorkspace.module.css'
import styles from './ExtensionsPage.module.css'

type McpServerDraft = {
  serverId: string
  name: string
  description: string
  transport: 'stdio' | 'streamable_http'
  command: string
  args: string
  cwd: string
  url: string
  bearerTokenEnvVar: string
}

const EMPTY_MCP_SERVER_DRAFT: McpServerDraft = {
  serverId: '',
  name: '',
  description: '',
  transport: 'stdio',
  command: '',
  args: '',
  cwd: '',
  url: '',
  bearerTokenEnvVar: '',
}

export function ExtensionsPage() {
  const navigate = useNavigate()
  const [mcpServerDraft, setMcpServerDraft] = useState<McpServerDraft>(EMPTY_MCP_SERVER_DRAFT)
  const [mcpServers, setMcpServers] = useState<McpRegistryServer[]>([])
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [isSavingRegistry, setIsSavingRegistry] = useState(false)
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

  useEffect(() => {
    void loadRegistry()
  }, [])

  async function loadRegistry() {
    try {
      setRegistryError(null)
      const response = await api.listMcpRegistry()
      setMcpServers(response.servers)
    } catch (error) {
      setRegistryError(error instanceof Error ? error.message : 'Failed to load MCP registry')
    }
  }

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

  const canAddMcpServer =
    mcpServerDraft.serverId.trim() !== '' &&
    (mcpServerDraft.transport === 'stdio' ? mcpServerDraft.command.trim() !== '' : mcpServerDraft.url.trim() !== '')

  async function handleSaveMcpServer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canAddMcpServer) return
    setIsSavingRegistry(true)
    try {
      const serverId = mcpServerDraft.serverId.trim()
      const transport =
        mcpServerDraft.transport === 'stdio'
          ? {
              type: 'stdio' as const,
              command: mcpServerDraft.command.trim(),
              args: splitArgs(mcpServerDraft.args),
              cwd: mcpServerDraft.cwd.trim() || undefined,
            }
          : {
              type: 'streamable_http' as const,
              url: mcpServerDraft.url.trim(),
              bearer_token_env_var: mcpServerDraft.bearerTokenEnvVar.trim() || undefined,
            }
      await api.upsertMcpRegistryServer({
        serverId,
        name: mcpServerDraft.name.trim() || serverId,
        description: mcpServerDraft.description.trim(),
        transport,
        installStatus: 'registered',
        trustStatus: 'untrusted',
        metadata: {},
        updatedAt: null,
      })
      setMcpServerDraft(EMPTY_MCP_SERVER_DRAFT)
      await loadRegistry()
    } catch (error) {
      setRegistryError(error instanceof Error ? error.message : 'Failed to save MCP server')
    } finally {
      setIsSavingRegistry(false)
    }
  }

  async function deleteServer(serverId: string) {
    try {
      setRegistryError(null)
      await api.deleteMcpRegistryServer(serverId)
      await loadRegistry()
    } catch (error) {
      setRegistryError(error instanceof Error ? error.message : 'Failed to delete MCP server')
    }
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
            <p className={styles.eyebrow}>Extensions</p>
            <h1 className={styles.title}>Global MCP registry</h1>
            <p className={styles.subtitle}>
              Register MCP server definitions once. Thread-specific enablement, tool policy, and runtime
              status live in each node's Info to Extensions panel.
            </p>
          </header>

          <section className={styles.mcpPanel} aria-labelledby="mcp-server-form-title">
            <div className={styles.mcpPanelHeader}>
              <div>
                <h2 id="mcp-server-form-title" className={styles.sectionTitle}>Register MCP server</h2>
                <p className={styles.sectionDescription}>
                  Registry health checks config validity, command availability, env vars, trust, and install status only.
                </p>
              </div>
            </div>

            {registryError ? <div className={styles.errorBanner}>{registryError}</div> : null}

            <form className={styles.mcpForm} onSubmit={handleSaveMcpServer}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Server ID</span>
                <input
                  className={styles.input}
                  value={mcpServerDraft.serverId}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, serverId: event.target.value }))}
                  placeholder="filesystem"
                />
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Transport</span>
                <select
                  className={styles.input}
                  value={mcpServerDraft.transport}
                  onChange={(event) =>
                    setMcpServerDraft((current) => ({ ...current, transport: event.target.value as McpServerDraft['transport'] }))
                  }
                >
                  <option value="stdio">stdio</option>
                  <option value="streamable_http">streamable HTTP</option>
                </select>
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>Display name</span>
                <input
                  className={styles.input}
                  value={mcpServerDraft.name}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Filesystem MCP"
                />
              </label>

              <label className={`${styles.field} ${styles.fieldWide}`}>
                <span className={styles.fieldLabel}>Description</span>
                <input
                  className={styles.input}
                  value={mcpServerDraft.description}
                  onChange={(event) => setMcpServerDraft((current) => ({ ...current, description: event.target.value }))}
                  placeholder="Reads selected project files"
                />
              </label>

              {mcpServerDraft.transport === 'stdio' ? (
                <>
                  <label className={`${styles.field} ${styles.fieldWide}`}>
                    <span className={styles.fieldLabel}>Command</span>
                    <input
                      className={styles.input}
                      value={mcpServerDraft.command}
                      onChange={(event) => setMcpServerDraft((current) => ({ ...current, command: event.target.value }))}
                      placeholder="npx"
                    />
                  </label>
                  <label className={`${styles.field} ${styles.fieldWide}`}>
                    <span className={styles.fieldLabel}>Args</span>
                    <input
                      className={styles.input}
                      value={mcpServerDraft.args}
                      onChange={(event) => setMcpServerDraft((current) => ({ ...current, args: event.target.value }))}
                      placeholder="-y @modelcontextprotocol/server-filesystem ."
                    />
                  </label>
                </>
              ) : (
                <>
                  <label className={`${styles.field} ${styles.fieldWide}`}>
                    <span className={styles.fieldLabel}>URL</span>
                    <input
                      className={styles.input}
                      value={mcpServerDraft.url}
                      onChange={(event) => setMcpServerDraft((current) => ({ ...current, url: event.target.value }))}
                      placeholder="https://mcp.example.com/mcp"
                    />
                  </label>
                  <label className={`${styles.field} ${styles.fieldWide}`}>
                    <span className={styles.fieldLabel}>Bearer token env var</span>
                    <input
                      className={styles.input}
                      value={mcpServerDraft.bearerTokenEnvVar}
                      onChange={(event) => setMcpServerDraft((current) => ({ ...current, bearerTokenEnvVar: event.target.value }))}
                      placeholder="LINEAR_API_KEY"
                    />
                  </label>
                </>
              )}

              <div className={styles.formActions}>
                <button type="submit" className={styles.primaryButton} disabled={!canAddMcpServer || isSavingRegistry}>
                  Save server
                </button>
              </div>
            </form>

            <div className={styles.mcpServerList} aria-label="Registered MCP servers">
              {mcpServers.length === 0 ? (
                <p className={styles.emptyMcpState}>No MCP servers registered yet.</p>
              ) : (
                mcpServers.map((server) => <McpRegistryCard key={server.serverId} server={server} onDelete={deleteServer} />)
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  )
}

function McpRegistryCard({ server, onDelete }: { server: McpRegistryServer; onDelete: (serverId: string) => void }) {
  const warnings = server.health?.warnings ?? []
  const errors = server.health?.errors ?? []
  const transportLabel = server.transport.type === 'streamable_http' ? 'streamable HTTP' : 'stdio'
  const target = useMemo(() => {
    if (server.transport.type === 'stdio') {
      return [server.transport.command, ...(Array.isArray(server.transport.args) ? server.transport.args : [])]
        .filter(Boolean)
        .join(' ')
    }
    return String(server.transport.url ?? '')
  }, [server.transport])

  return (
    <article className={styles.mcpServerCard}>
      <div className={styles.cardHeader}>
        <div>
          <h3 className={styles.cardTitle}>{server.name}</h3>
          <p className={styles.description}>{server.description || server.serverId}</p>
        </div>
        <span className={styles.badge}>{transportLabel}</span>
      </div>
      <code className={styles.serverTarget}>{target}</code>
      <div className={styles.healthRow}>
        <span className={server.health?.valid ? styles.healthOk : styles.healthBad}>
          {server.health?.valid ? 'Config valid' : 'Config invalid'}
        </span>
        <span>{server.health?.installStatus ?? server.installStatus}</span>
        <span>{server.health?.trustStatus ?? server.trustStatus}</span>
      </div>
      {[...errors, ...warnings].map((issue) => (
        <p key={`${issue.code}:${issue.message}`} className={styles.healthIssue}>{issue.message}</p>
      ))}
      <div className={styles.formActions}>
        <button type="button" className={styles.secondaryButton} onClick={() => void onDelete(server.serverId)}>
          Delete
        </button>
      </div>
    </article>
  )
}

function splitArgs(raw: string): string[] {
  return raw.split(/\s+/).map((part) => part.trim()).filter(Boolean)
}

