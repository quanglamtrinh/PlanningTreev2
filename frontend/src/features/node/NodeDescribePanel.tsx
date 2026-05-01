import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ChangedFileRecord, DetailState, McpRegistryServer, McpThreadProfile, McpThreadRole, McpTransportType, NodeRecord, SkillMetadata, SkillThreadProfile } from '../../api/types'
import { InfoWorkspaceMarkdownEditor } from './InfoWorkspaceMarkdownEditor'
import { formatNodeDisplayIndex } from '../../utils/nodeDisplayIndex'
import { DocumentRichViewContent } from '../markdown/DocumentRichView'
import styles from './NodeDetailCard.module.css'

const INFO_TAB_DOCS_PATHS = [
  'docs/overview.md',
  'docs/setup.md',
  'docs/architecture.md',
  'docs/codebase-map.md',
  'docs/development-notes.md',
  'task/context.md',
  'task/handoff.md',
] as const

const INFO_TAB_CONTEXT_PATH = 'task/context.md'
const INFO_TAB_CONTEXT_FALLBACK = `# Context

No workflow context is available for this thread yet.
`

function mcpTransportBadge(transport: McpRegistryServer['transport']): string {
  const t = transport?.type as McpTransportType | undefined
  if (t === 'stdio') {
    return 'stdio'
  }
  if (t === 'streamable_http') {
    return 'HTTP'
  }
  return t ? String(t) : 'MCP'
}

type InfoWorkspaceFileTarget = {
  relativePath: string
  scope: 'workspace' | 'root_node' | 'node'
}

/** Maps list row path to workspace-text-file API target. */
export function infoTabListPathToWorkspaceTarget(
  variant: 'docs' | 'skills',
  listPath: string,
): InfoWorkspaceFileTarget {
  const trimmed = listPath.replace(/^[/\\]+/, '')
  if (variant === 'skills') {
    return { relativePath: `.codex/skills/${trimmed}`, scope: 'workspace' }
  }
  if (trimmed.startsWith('task/')) {
    return { relativePath: trimmed.slice('task/'.length), scope: 'node' }
  }
  return { relativePath: trimmed, scope: 'root_node' }
}

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
  onSelectPath,
  'data-testid': testId,
}: {
  paths: readonly string[]
  variant: 'docs' | 'skills'
  onSelectPath: (path: string) => void
  'data-testid'?: string
}) {
  return (
    <ul className={styles.infoPathList} data-testid={testId}>
      {paths.map((path) => (
        <li key={path} className={styles.infoPathItem}>
          <button
            type="button"
            className={styles.infoPathHit}
            onClick={() => onSelectPath(path)}
            aria-label={`Open ${path} in markdown editor`}
          >
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
          </button>
        </li>
      ))}
    </ul>
  )
}

type InfoTabMcpRole = Extract<McpThreadRole, 'ask_planning' | 'execution' | 'audit' | 'root'>

type InfoTabMcpRoleBlock = {
  role: InfoTabMcpRole
  title: string
  description: string
}

type McpRolePanelState = {
  profile: McpThreadProfile | null
  error: string | null
}

const INFO_TAB_MCP_ROLE_BLOCKS: readonly InfoTabMcpRoleBlock[] = [
  {
    role: 'ask_planning',
    title: 'Ask',
    description: 'Planning and clarification thread for this node.',
  },
  {
    role: 'execution',
    title: 'Execution',
    description: 'Implementation thread that applies changes.',
  },
  {
    role: 'audit',
    title: 'Audit',
    description: 'Review thread for checking the execution result.',
  },
]

type InfoTabSkillRole = Extract<McpThreadRole, 'ask_planning' | 'execution' | 'audit' | 'package_review' | 'root'>

type InfoTabSkillBlock = {
  role: InfoTabSkillRole
  title: string
  description: string
}

type SkillRolePanelState = {
  profile: SkillThreadProfile | null
  error: string | null
}

const INFO_TAB_SKILL_BLOCKS: readonly InfoTabSkillBlock[] = [
  {
    role: 'root',
    title: 'Project prep',
    description: 'Root thread for codebase scans, docs, and handoff preparation.',
  },
  {
    role: 'ask_planning',
    title: 'Ask',
    description: 'Planning and clarification thread for this node.',
  },
  {
    role: 'execution',
    title: 'Execution',
    description: 'Implementation thread that applies changes.',
  },
  {
    role: 'audit',
    title: 'Audit',
    description: 'Review thread for checking the execution result.',
  },
]

function createEmptySkillRoleStates(roleBlocks: readonly InfoTabSkillBlock[]): Record<InfoTabSkillRole, SkillRolePanelState> {
  return roleBlocks.reduce(
    (states, { role }) => {
      states[role] = { profile: null, error: null }
      return states
    },
    {} as Record<InfoTabSkillRole, SkillRolePanelState>,
  )
}

function skillDisplayName(skill: SkillMetadata): string {
  return skill.interface?.displayName?.trim() || skill.name
}

function skillDescription(skill: SkillMetadata): string {
  return skill.interface?.shortDescription?.trim() || skill.description || skill.path
}

function skillDependencyLabel(skill: SkillMetadata): string | null {
  const count = skill.dependencies?.tools?.length ?? 0
  if (count <= 0) {
    return null
  }
  return `${count} dep${count === 1 ? '' : 's'}`
}

function ThreadSkillsPanel({
  projectId,
  nodeId,
  roleBlocks = INFO_TAB_SKILL_BLOCKS,
}: {
  projectId: string
  nodeId: string
  roleBlocks?: readonly InfoTabSkillBlock[]
}) {
  const [registry, setRegistry] = useState<SkillMetadata[]>([])
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [roleStates, setRoleStates] = useState<Record<InfoTabSkillRole, SkillRolePanelState>>(() =>
    createEmptySkillRoleStates(roleBlocks),
  )

  useEffect(() => {
    let cancelled = false

    async function load() {
      setRegistryError(null)
      setRegistry([])
      setRoleStates(createEmptySkillRoleStates(roleBlocks))
      try {
        const [registryResponse, roleResponses] = await Promise.all([
          api.listSkillsRegistry(projectId),
          Promise.all(
            roleBlocks.map(async ({ role }) => {
              try {
                const profileResponse = await api.readSkillThreadProfile(projectId, nodeId, role)
                return { role, state: { profile: profileResponse.profile, error: null } }
              } catch (loadError) {
                return {
                  role,
                  state: {
                    profile: null,
                    error: mcpErrorMessage(loadError, 'Failed to load skills profile'),
                  },
                }
              }
            }),
          ),
        ])
        if (cancelled) {
          return
        }
        const nextRoleStates = createEmptySkillRoleStates(roleBlocks)
        roleResponses.forEach(({ role, state }) => {
          nextRoleStates[role] = state
        })
        setRegistry(registryResponse.data.flatMap((entry) => entry.skills))
        const errors = registryResponse.data.flatMap((entry) => entry.errors ?? [])
        setRegistryError(errors.length > 0 ? `${errors.length} skill catalog issue${errors.length === 1 ? '' : 's'} found.` : null)
        setRoleStates(nextRoleStates)
      } catch (loadError) {
        if (cancelled) {
          return
        }
        setRegistry([])
        setRegistryError(mcpErrorMessage(loadError, 'Failed to load skills registry'))
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [projectId, nodeId, roleBlocks])

  async function patchProfile(role: InfoTabSkillRole, patch: Partial<SkillThreadProfile>) {
    try {
      const response = await api.updateSkillThreadProfile(projectId, nodeId, role, patch)
      setRoleStates((current) => ({ ...current, [role]: { profile: response.profile, error: null } }))
    } catch (updateError) {
      setRoleStates((current) => ({
        ...current,
        [role]: {
          ...current[role],
          error: mcpErrorMessage(updateError, 'Failed to update skills profile'),
        },
      }))
    }
  }

  function toggleSkill(role: InfoTabSkillRole, state: SkillRolePanelState, skill: SkillMetadata) {
    const current = state.profile?.skills?.[skill.path]
    void patchProfile(role, {
      skills: {
        ...(state.profile?.skills ?? {}),
        [skill.path]: {
          enabled: !current?.enabled,
          activationMode: current?.activationMode ?? 'alwaysOnForRole',
          name: skill.name,
          scope: skill.scope,
          updatedAt: current?.updatedAt ?? null,
        },
      },
    })
  }

  return (
    <div className={styles.infoMcpPanel} data-testid="info-tab-skills-panel">
      <div className={styles.infoMcpHeaderRow}>
        <p className={styles.infoExtensionDescription}>
          Global skills are discovered from Codex for this project. Enable skills separately for each workflow thread.
        </p>
      </div>

      {registryError ? <p className={styles.infoMcpError}>{registryError}</p> : null}

      <div className={styles.infoMcpRoleGrid}>
        {roleBlocks.map(({ role, title, description }) => {
          const state = roleStates[role]
          const profile = state.profile
          return (
            <section key={role} className={styles.infoMcpRoleBlock} data-testid={`info-tab-skills-role-${role}`}>
              <div className={styles.infoMcpRoleHeader}>
                <div>
                  <h3 className={styles.infoMcpTitle}>{title}</h3>
                  <p className={styles.infoExtensionDescription}>{description}</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={Boolean(profile?.skillsEnabled)}
                  disabled={!profile}
                  className={profile?.skillsEnabled ? styles.infoExtensionToggleOn : styles.infoExtensionToggle}
                  onClick={() => void patchProfile(role, { skillsEnabled: !profile?.skillsEnabled })}
                >
                  <span className={styles.infoExtensionToggleTrack} aria-hidden>
                    <span className={styles.infoExtensionToggleThumb} />
                  </span>
                  <span className={styles.infoExtensionToggleLabel}>{profile?.skillsEnabled ? 'Skills on' : 'Skills off'}</span>
                </button>
              </div>

              {state.error ? <p className={styles.infoMcpError}>{state.error}</p> : null}

              <p className={styles.infoMcpListHeading}>Always on for role</p>
              <ul className={styles.infoExtensionList} data-testid={`info-tab-skills-${role}`}>
                {registry.length === 0 ? (
                  <li className={styles.infoExtensionItem}>
                    <p className={styles.changedFilesEmpty}>No Codex skills found for this project.</p>
                  </li>
                ) : (
                  registry.map((skill) => {
                    const entry = profile?.skills?.[skill.path]
                    const enabled = Boolean(entry?.enabled)
                    const dependencyLabel = skillDependencyLabel(skill)
                    return (
                      <li key={skill.path} className={styles.infoExtensionItem}>
                        <div className={styles.infoExtensionCopy}>
                          <div className={styles.infoExtensionTitleRow}>
                            <span className={styles.infoExtensionName}>{skillDisplayName(skill)}</span>
                            <span className={styles.infoExtensionBadge}>{skill.scope}</span>
                            {!skill.enabled ? <span className={styles.infoExtensionBadge}>disabled</span> : null}
                            {dependencyLabel ? <span className={styles.infoExtensionBadge}>{dependencyLabel}</span> : null}
                          </div>
                          <p className={styles.infoExtensionDescription}>{skillDescription(skill)}</p>
                          <p className={styles.infoExtensionDescription}>{skill.path}</p>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={enabled}
                          disabled={!profile || !skill.enabled}
                          className={enabled ? styles.infoExtensionToggleOn : styles.infoExtensionToggle}
                          onClick={() => toggleSkill(role, state, skill)}
                        >
                          <span className={styles.infoExtensionToggleTrack} aria-hidden>
                            <span className={styles.infoExtensionToggleThumb} />
                          </span>
                          <span className={styles.infoExtensionToggleLabel}>{enabled ? 'On' : 'Off'}</span>
                        </button>
                      </li>
                    )
                  })
                )}
              </ul>
            </section>
          )
        })}
      </div>
    </div>
  )
}


export const ROOT_INFO_TAB_MCP_ROLE_BLOCKS: readonly InfoTabMcpRoleBlock[] = [
  {
    role: 'root',
    title: 'Root',
    description: 'Project preparation thread for codebase scans, docs, and knowledge artifacts.',
  },
]

function createEmptyMcpRoleStates(roleBlocks: readonly InfoTabMcpRoleBlock[]): Record<InfoTabMcpRole, McpRolePanelState> {
  return roleBlocks.reduce(
    (states, { role }) => {
      states[role] = { profile: null, error: null }
      return states
    },
    {} as Record<InfoTabMcpRole, McpRolePanelState>,
  )
}

function mcpErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function ThreadMcpExtensionsPanel({
  projectId,
  nodeId,
  roleBlocks = INFO_TAB_MCP_ROLE_BLOCKS,
}: {
  projectId: string
  nodeId: string
  roleBlocks?: readonly InfoTabMcpRoleBlock[]
}) {
  const [registry, setRegistry] = useState<McpRegistryServer[]>([])
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [roleStates, setRoleStates] = useState<Record<InfoTabMcpRole, McpRolePanelState>>(() =>
    createEmptyMcpRoleStates(roleBlocks),
  )

  useEffect(() => {
    let cancelled = false

    async function load() {
      setRegistryError(null)
      setRegistry([])
      setRoleStates(createEmptyMcpRoleStates(roleBlocks))

      try {
        const [registryResponse, roleResponses] = await Promise.all([
          api.listMcpRegistry(),
          Promise.all(
            roleBlocks.map(async ({ role }) => {
              try {
                const profileResponse = await api.readMcpThreadProfile(projectId, nodeId, role)
                return {
                  role,
                  state: {
                    profile: profileResponse.profile,
                    error: null,
                  },
                }
              } catch (loadError) {
                return {
                  role,
                  state: {
                    profile: null,
                    error: mcpErrorMessage(loadError, 'Failed to load MCP profile'),
                  },
                }
              }
            }),
          ),
        ])
        if (cancelled) {
          return
        }

        const nextRoleStates = createEmptyMcpRoleStates(roleBlocks)
        roleResponses.forEach(({ role, state }) => {
          nextRoleStates[role] = state
        })
        setRegistry(registryResponse.servers)
        setRoleStates(nextRoleStates)
      } catch (loadError) {
        if (cancelled) {
          return
        }
        setRegistry([])
        setRegistryError(mcpErrorMessage(loadError, 'Failed to load MCP registry'))
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [projectId, nodeId, roleBlocks])

  async function patchProfile(role: InfoTabMcpRole, patch: Partial<McpThreadProfile>) {
    try {
      const response = await api.updateMcpThreadProfile(projectId, nodeId, role, patch)
      setRoleStates((current) => ({
        ...current,
        [role]: {
          profile: response.profile,
          error: null,
        },
      }))
    } catch (updateError) {
      setRoleStates((current) => ({
        ...current,
        [role]: {
          ...current[role],
          error: mcpErrorMessage(updateError, 'Failed to update MCP profile'),
        },
      }))
    }
  }

  function toggleServer(role: InfoTabMcpRole, state: McpRolePanelState, serverId: string) {
    const current = state.profile?.servers?.[serverId]
    void patchProfile(role, {
      servers: {
        ...(state.profile?.servers ?? {}),
        [serverId]: {
          enabled: !current?.enabled,
          enabledTools: current?.enabledTools ?? [],
          disabledTools: current?.disabledTools ?? [],
          approvalMode: current?.approvalMode ?? state.profile?.approvalMode ?? 'never',
          toolApproval: current?.toolApproval ?? {},
        },
      },
    })
  }

  return (
    <div className={styles.infoMcpPanel} data-testid="info-tab-mcp-extensions">
      <div className={styles.infoMcpHeaderRow}>
        <p className={styles.infoExtensionDescription}>
          Global servers are managed in <strong>Graph - Extensions</strong>. Configure MCP separately
          for each workflow thread below.
        </p>
      </div>

      {registryError ? <p className={styles.infoMcpError}>{registryError}</p> : null}

      <div className={styles.infoMcpRoleGrid}>
        {roleBlocks.map(({ role, title, description }) => {
          const state = roleStates[role]
          const profile = state.profile
          return (
            <section key={role} className={styles.infoMcpRoleBlock} data-testid={`info-tab-mcp-role-${role}`}>
              <div className={styles.infoMcpRoleHeader}>
                <div>
                  <h3 className={styles.infoMcpTitle}>{title}</h3>
                  <p className={styles.infoExtensionDescription}>{description}</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={Boolean(profile?.mcpEnabled)}
                  disabled={!profile}
                  className={profile?.mcpEnabled ? styles.infoExtensionToggleOn : styles.infoExtensionToggle}
                  onClick={() => void patchProfile(role, { mcpEnabled: !profile?.mcpEnabled })}
                >
                  <span className={styles.infoExtensionToggleTrack} aria-hidden>
                    <span className={styles.infoExtensionToggleThumb} />
                  </span>
                  <span className={styles.infoExtensionToggleLabel}>{profile?.mcpEnabled ? 'MCP on' : 'MCP off'}</span>
                </button>
              </div>

              {state.error ? <p className={styles.infoMcpError}>{state.error}</p> : null}

              <p className={styles.infoMcpListHeading}>Include servers</p>
              <ul className={styles.infoExtensionList} data-testid={`info-tab-extensions-${role}`}>
                {registry.length === 0 ? (
                  <li className={styles.infoExtensionItem}>
                    <p className={styles.changedFilesEmpty}>No global MCP servers registered yet.</p>
                  </li>
                ) : (
                  registry.map((server) => {
                    const enabled = Boolean(profile?.servers?.[server.serverId]?.enabled)
                    const desc = server.description.trim() || `Server id: ${server.serverId}`
                    return (
                      <li key={server.serverId} className={styles.infoExtensionItem}>
                        <div className={styles.infoExtensionCopy}>
                          <div className={styles.infoExtensionTitleRow}>
                            <span className={styles.infoExtensionName}>{server.name}</span>
                            <span className={styles.infoExtensionBadge}>{mcpTransportBadge(server.transport)}</span>
                          </div>
                          <p className={styles.infoExtensionDescription}>{desc}</p>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={enabled}
                          disabled={!profile}
                          className={enabled ? styles.infoExtensionToggleOn : styles.infoExtensionToggle}
                          onClick={() => toggleServer(role, state, server.serverId)}
                        >
                          <span className={styles.infoExtensionToggleTrack} aria-hidden>
                            <span className={styles.infoExtensionToggleThumb} />
                          </span>
                          <span className={styles.infoExtensionToggleLabel}>{enabled ? 'On' : 'Off'}</span>
                        </button>
                      </li>
                    )
                  })
                )}
              </ul>

            </section>
          )
        })}
      </div>
    </div>
  )
}

type Props = {
  node: NodeRecord
  projectId: string
  detailState?: DetailState | null
  workflowContextMarkdown?: string | null
  onResetToBefore?: () => void | Promise<void>
  onResetToResult?: () => void | Promise<void>
  isResetting?: boolean
  mcpRoleBlocks?: readonly InfoTabMcpRoleBlock[]
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
  workflowContextMarkdown = null,
  onResetToBefore,
  onResetToResult,
  isResetting = false,
  mcpRoleBlocks = INFO_TAB_MCP_ROLE_BLOCKS,
}: Props) {
  const [openInfoPath, setOpenInfoPath] = useState<{
    variant: 'docs' | 'skills'
    path: string
  } | null>(null)

  const initialSha = displaySha(detailState?.initial_sha)
  const headSha = displaySha(detailState?.head_sha)
  const currentHead = displaySha(detailState?.current_head_sha)
  const commitMessage = detailState?.commit_message?.trim()
    ? detailState.commit_message
    : '—'
  const changedFiles = normalizeChangedFiles(detailState?.changed_files)

  const present = detailState?.task_present_in_current_workspace
  const taskMissing = present === false
  const displayIndex = formatNodeDisplayIndex(node)

  if (openInfoPath) {
    if (openInfoPath.variant === 'docs' && openInfoPath.path === INFO_TAB_CONTEXT_PATH) {
      const content = workflowContextMarkdown?.trim() ? workflowContextMarkdown : INFO_TAB_CONTEXT_FALLBACK
      return (
        <div className={styles.describeDocumentRoot}>
          <div className={styles.describeDocumentSheet}>
            <div className={`${styles.describeInfoEditorHost} ${styles.documentPanel}`}>
              <div className={styles.infoWorkspaceEditorToolbar}>
                <button type="button" className={styles.describeWorkspaceButtonOutline} onClick={() => setOpenInfoPath(null)}>
                  {'<- Back to info'}
                </button>
                <div className={styles.documentFileLabelCell}>
                  <span className={styles.documentFileLabelIcon} aria-hidden="true">
                    <svg
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      width="13"
                      height="13"
                    >
                      <path d="M4 2h6l3 3v9a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" />
                      <path d="M10 2v4h3" />
                    </svg>
                  </span>
                  <span className={styles.documentFileLabel}>{INFO_TAB_CONTEXT_PATH}</span>
                </div>
              </div>
              <div className={styles.editorSurface}>
                <div className={`${styles.editorSurfaceHeader} ${styles.contextEditorSurfaceHeader}`} />
                <div className={styles.editorSurfaceBody}>
                  <DocumentRichViewContent
                    content={content}
                    testId="info-context-rich-view"
                    className={`${styles.richViewSurface} ${styles.contextRichViewSurface}`}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )
    }
    const workspaceTarget = infoTabListPathToWorkspaceTarget(openInfoPath.variant, openInfoPath.path)
    return (
      <div className={styles.describeDocumentRoot}>
        <div className={styles.describeDocumentSheet}>
          <InfoWorkspaceMarkdownEditor
            projectId={projectId}
            workspaceRelativePath={workspaceTarget.relativePath}
            workspaceScope={workspaceTarget.scope}
            nodeId={workspaceTarget.scope === 'node' ? node.node_id : null}
            displayPath={openInfoPath.path}
            onClose={() => setOpenInfoPath(null)}
          />
        </div>
      </div>
    )
  }

  return (
    <div className={styles.describeDocumentRoot}>
      <div className={styles.describeDocumentSheet}>
        <div className={styles.describePanel}>
          <div className={styles.describeDocHero}>
            <p className={styles.eyebrow}>
              {displayIndex ? `${displayIndex} - Node` : 'Node'}
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
              <InfoPathList
                variant="docs"
                paths={INFO_TAB_DOCS_PATHS}
                data-testid="info-tab-docs-paths"
                onSelectPath={(path) => setOpenInfoPath({ variant: 'docs', path })}
              />
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
              <ThreadSkillsPanel projectId={projectId} nodeId={node.node_id} />
            </div>
          </div>

          <div className={styles.describeDocSection}>
            <div className={styles.describeExtensionsSection}>
              <h2 className={styles.describeSectionTitle}>Extensions</h2>
              <ThreadMcpExtensionsPanel projectId={projectId} nodeId={node.node_id} roleBlocks={mcpRoleBlocks} />
            </div>
          </div>

          {taskMissing ? (
            <div className={styles.describeDocSection}>
              <div className={styles.describeTaskMissingBanner} role="note">
                This task&apos;s checkpoint commits are not on the current branch history. You may
                have moved the workspace with a hard reset. Resets may fail until the repo state
                matches a known checkpoint.
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
                  disabled={isResetting}
                  onClick={() => void onResetToBefore?.()}
                >
                  {isResetting ? 'Resetting…' : 'Reset to before this task'}
                </button>
                <button
                  type="button"
                  className={styles.describeWorkspaceButtonPrimary}
                  disabled={isResetting}
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
