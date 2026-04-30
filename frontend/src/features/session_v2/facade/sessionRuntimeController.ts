import {
  forkThreadV2,
  initializeSessionV2,
  interruptTurnV2,
  listLoadedThreadsV2,
  listModelsV2,
  listPendingRequestsV2,
  listThreadsV2,
  listThreadTurnsV2,
  getThreadJournalHeadV2,
  readThreadV2,
  rejectPendingRequestV2,
  resolvePendingRequestV2,
  resumeThreadV2,
  startThreadV2,
  startTurnV2,
  steerTurnV2,
  type SessionModelEntryV2,
} from '../api/client'
import type { ComposerRequestedPolicy, ComposerSubmitPayload } from '../components/ComposerPane'
import type {
  PendingServerRequest,
  SessionError,
  SessionInputAction,
  SessionThread,
  SessionTurn,
  ThreadCreationPolicy,
  TurnExecutionPolicy,
  TurnStartRequestV4,
} from '../contracts'
import type { SetThreadTurnsOptions, ThreadSessionStoreState } from '../store/threadSessionStore'

type AsyncScope = 'bootstrap' | 'selectThread' | 'hydrateThread' | 'loadModels' | 'pollPending'

type AsyncScopeTokens = Record<AsyncScope, number>

export type ComposerModelOption = {
  value: string
  label: string
  isDefault: boolean
}

export const DEFAULT_CODEX_MODEL_OPTION: ComposerModelOption = {
  value: 'gpt-5.3-codex',
  label: 'GPT-5.3-Codex',
  isDefault: true,
}

export const CODEX_MODEL_FALLBACK_OPTIONS: ComposerModelOption[] = [
  DEFAULT_CODEX_MODEL_OPTION,
  { value: 'gpt-5.2', label: 'GPT-5.2', isDefault: false },
  { value: 'gpt-5.4-mini', label: 'GPT-5.4 Mini', isDefault: false },
  { value: 'gpt-5.4', label: 'GPT-5.4', isDefault: false },
]

export type SessionBootstrapPolicy = {
  autoSelectInitialThread: boolean
  autoCreateThreadWhenEmpty: boolean
  threadCreationPolicy?: ThreadCreationPolicy
}

const DEFAULT_BOOTSTRAP_POLICY: SessionBootstrapPolicy = {
  autoSelectInitialThread: true,
  autoCreateThreadWhenEmpty: true,
}

export type RuntimeSnapshot = {
  activeThreadId: string | null
  activeTurns: SessionTurn[]
  activeRunningTurn: SessionTurn | null
  selectedModel: string | null
}

type RuntimeApi = {
  forkThread: typeof forkThreadV2
  initializeSession: typeof initializeSessionV2
  interruptTurn: typeof interruptTurnV2
  listLoadedThreads: typeof listLoadedThreadsV2
  listModels: typeof listModelsV2
  listPendingRequests: typeof listPendingRequestsV2
  listThreads: typeof listThreadsV2
  listThreadTurns: typeof listThreadTurnsV2
  getThreadJournalHead: typeof getThreadJournalHeadV2
  readThread: typeof readThreadV2
  rejectPendingRequest: typeof rejectPendingRequestV2
  resolvePendingRequest: typeof resolvePendingRequestV2
  resumeThread: typeof resumeThreadV2
  startThread: typeof startThreadV2
  startTurn: typeof startTurnV2
  steerTurn: typeof steerTurnV2
}

export type SessionRuntimeControllerDependencies = {
  getThreadState: () => ThreadSessionStoreState
  getRuntimeSnapshot: () => RuntimeSnapshot
  setThreadList: (threads: SessionThread[]) => void
  setReplayCursor: (threadId: string, lastEventSeq: number, lastEventId: string | null) => void
  upsertThread: (thread: SessionThread, options?: { preserveUpdatedAt?: boolean }) => void
  markThreadActivity: (threadId: string, updatedAt?: number) => void
  setActiveThreadId: (threadId: string | null) => void
  setThreadTurns: (threadId: string, turns: SessionTurn[], options?: SetThreadTurnsOptions) => void
  hydratePendingRequests: (rows: PendingServerRequest[]) => void
  markPendingRequestSubmitted: (requestId: string) => void
  setConnectionPhase: (phase: 'disconnected' | 'connecting' | 'initialized' | 'error') => void
  setConnectionInitialized: (clientName: string | null, serverVersion: string | null) => void
  setConnectionError: (error: SessionError) => void
  setRuntimeError: (message: string | null) => void
  setIsBootstrapping: (next: boolean) => void
  setIsModelLoading: (next: boolean) => void
  setModelOptions: (next: ComposerModelOption[]) => void
  setLastPendingPollAtMs: (value: number | null) => void
  isDisposed: () => boolean
  api?: Partial<RuntimeApi>
}

export type HydrateOptions = {
  force?: boolean
  replaceProjection?: boolean
  isCurrent?: () => boolean
}

export type EnsureThreadReadyOptions = {
  forceHydrate?: boolean
  isCurrent?: () => boolean
}

export type SessionRuntimeController = {
  bootstrap: (policy?: Partial<SessionBootstrapPolicy>) => Promise<void>
  hydrateThreadState: (threadId: string, options?: HydrateOptions) => Promise<void>
  ensureThreadReady: (threadId: string, options?: EnsureThreadReadyOptions) => Promise<void>
  loadModels: () => Promise<void>
  pollPendingRequests: (options?: { surfaceErrors?: boolean }) => Promise<void>
  selectThread: (threadId: string | null) => Promise<void>
  createThread: (policy?: ThreadCreationPolicy) => Promise<void>
  forkThread: (threadId: string) => Promise<void>
  refreshThreads: () => Promise<void>
  submitSessionAction: (action: SessionInputAction) => Promise<void>
  submit: (payload: ComposerSubmitPayload, policy?: TurnExecutionPolicy, context?: Extract<SessionInputAction, { type: 'turn.start' }>['context']) => Promise<void>
  interrupt: () => Promise<void>
  resetHydratedState: () => void
  dispose: () => void
}

export function createSessionActionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function upsertTurnList(existing: SessionTurn[], nextTurn: SessionTurn): SessionTurn[] {
  const index = existing.findIndex((turn) => turn.id === nextTurn.id)
  if (index < 0) {
    return [...existing, nextTurn]
  }
  const updated = [...existing]
  updated[index] = nextTurn
  return updated
}

function normalizeModelOption(entry: SessionModelEntryV2): ComposerModelOption | null {
  const modelValue = typeof entry.model === 'string' ? entry.model.trim() : ''
  const idValue = typeof entry.id === 'string' ? entry.id.trim() : ''
  const model = modelValue || idValue
  if (!model) {
    return null
  }
  const displayName = typeof entry.displayName === 'string' ? entry.displayName.trim() : ''
  return {
    value: model,
    label: displayName || model,
    isDefault: Boolean(entry.isDefault) || model === DEFAULT_CODEX_MODEL_OPTION.value,
  }
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

function resolveTurnModel(
  policy: TurnExecutionPolicy | undefined,
  payload: ComposerSubmitPayload,
  selectedModel: string | null,
): string | null {
  return (
    nonEmptyString(policy?.model) ??
    nonEmptyString(payload.requestedPolicy?.model) ??
    nonEmptyString(selectedModel)
  )
}

function resolveTurnStartPolicy(
  policy: TurnExecutionPolicy | undefined,
  payload: ComposerSubmitPayload,
  selectedModel: string | null,
): TurnExecutionPolicy | undefined {
  const derivedPolicy = deriveTurnPolicyFromRequestedPolicy(payload.requestedPolicy)
  const nextPolicy: TurnExecutionPolicy = {
    ...derivedPolicy,
    ...(policy ?? {}),
  }
  delete nextPolicy.model
  const model = resolveTurnModel(policy, payload, selectedModel)
  if (model) {
    nextPolicy.model = model
  }
  return Object.keys(nextPolicy).length > 0 ? nextPolicy : undefined
}

function deriveTurnPolicyFromRequestedPolicy(
  requestedPolicy: ComposerRequestedPolicy | null | undefined,
): TurnExecutionPolicy {
  const nextPolicy: TurnExecutionPolicy = {}
  if (requestedPolicy?.effort === 'extra-high') {
    nextPolicy.effort = 'xhigh'
  } else if (requestedPolicy?.effort) {
    nextPolicy.effort = requestedPolicy.effort
  }

  const accessMode = requestedPolicy?.accessMode ?? 'full-access'
  if (accessMode === 'full-access') {
    nextPolicy.approvalPolicy = 'never'
    nextPolicy.sandboxPolicy = { type: 'dangerFullAccess' }
  } else if (accessMode === 'default-permissions') {
    nextPolicy.approvalPolicy = 'on-request'
    nextPolicy.sandboxPolicy = { type: 'workspaceWrite' }
  } else if (accessMode === 'read-only') {
    nextPolicy.approvalPolicy = 'on-request'
    nextPolicy.sandboxPolicy = { type: 'readOnly' }
  }

  return nextPolicy
}

function assertNever(value: never): never {
  throw new Error(`Unhandled session input action: ${JSON.stringify(value)}`)
}

function defaultApi(): RuntimeApi {
  return {
    forkThread: forkThreadV2,
    initializeSession: initializeSessionV2,
    interruptTurn: interruptTurnV2,
    listLoadedThreads: listLoadedThreadsV2,
    listModels: listModelsV2,
    listPendingRequests: listPendingRequestsV2,
    listThreads: listThreadsV2,
    listThreadTurns: listThreadTurnsV2,
    getThreadJournalHead: getThreadJournalHeadV2,
    readThread: readThreadV2,
    rejectPendingRequest: rejectPendingRequestV2,
    resolvePendingRequest: resolvePendingRequestV2,
    resumeThread: resumeThreadV2,
    startThread: startThreadV2,
    startTurn: startTurnV2,
    steerTurn: steerTurnV2,
  }
}

function resolveBootstrapPolicy(
  policy?: Partial<SessionBootstrapPolicy>,
): SessionBootstrapPolicy {
  return {
    autoSelectInitialThread:
      policy?.autoSelectInitialThread ?? DEFAULT_BOOTSTRAP_POLICY.autoSelectInitialThread,
    autoCreateThreadWhenEmpty:
      policy?.autoCreateThreadWhenEmpty ?? DEFAULT_BOOTSTRAP_POLICY.autoCreateThreadWhenEmpty,
    threadCreationPolicy: policy?.threadCreationPolicy,
  }
}

function isSessionRuntimeTraceEnabled(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    if (window.location.search.includes('debugSession=1')) {
      return true
    }
    return window.localStorage.getItem('sessionV2Trace') === '1'
  } catch {
    return false
  }
}

function traceSessionRuntime(message: string, payload?: Record<string, unknown>): void {
  if (!isSessionRuntimeTraceEnabled()) {
    return
  }
  if (payload) {
    console.info(`[session-v2-runtime] ${message}`, payload)
    return
  }
  console.info(`[session-v2-runtime] ${message}`)
}

export function createSessionRuntimeController(
  dependencies: SessionRuntimeControllerDependencies,
): SessionRuntimeController {
  const api = { ...defaultApi(), ...(dependencies.api ?? {}) }
  const hydratedThreadIds = new Set<string>()
  const scopeTokens: AsyncScopeTokens = {
    bootstrap: 0,
    selectThread: 0,
    hydrateThread: 0,
    loadModels: 0,
    pollPending: 0,
  }
  let selectionIntent = 0
  let disposed = false

  const isControllerAlive = () => !disposed && !dependencies.isDisposed()

  const beginScope = (scope: AsyncScope): number => {
    scopeTokens[scope] += 1
    return scopeTokens[scope]
  }

  const isScopeCurrent = (scope: AsyncScope, token: number): boolean => {
    return isControllerAlive() && scopeTokens[scope] === token
  }

  const buildGuard = (scope: AsyncScope): { token: number; isCurrent: () => boolean } => {
    const token = beginScope(scope)
    return {
      token,
      isCurrent: () => isScopeCurrent(scope, token),
    }
  }

  const ensureStillCurrent = (guard?: () => boolean): boolean => {
    if (!isControllerAlive()) {
      return false
    }
    if (guard && !guard()) {
      return false
    }
    return true
  }

  const listTurnsForHydrate = async (
    threadId: string,
    isCurrent: () => boolean,
  ): Promise<SessionTurn[]> => {
    const turns: SessionTurn[] = []
    let cursor: string | null = null
    for (let page = 0; page < 20; page += 1) {
      const listed = await api.listThreadTurns(threadId, {
        cursor,
        limit: 100,
      })
      if (!isCurrent()) {
        return turns
      }
      const pageTurns = Array.isArray(listed.data) ? listed.data : []
      turns.push(...pageTurns)
      if (!listed.nextCursor || pageTurns.length === 0) {
        break
      }
      cursor = listed.nextCursor
    }
    return turns
  }

  const hydrateThreadState = async (threadId: string, options?: HydrateOptions): Promise<void> => {
    if (!options?.force && hydratedThreadIds.has(threadId)) {
      traceSessionRuntime('hydrate skipped: already hydrated', {
        threadId,
      })
      return
    }

    traceSessionRuntime('hydrate start', {
      threadId,
      force: Boolean(options?.force),
      replaceProjection: Boolean(options?.replaceProjection),
    })
    const guard = buildGuard('hydrateThread')
    const isCurrent = () => guard.isCurrent() && ensureStillCurrent(options?.isCurrent)

    const read = await api.readThread(threadId, true)
    if (!isCurrent()) {
      traceSessionRuntime('hydrate aborted after read: stale scope', {
        threadId,
      })
      return
    }
    dependencies.upsertThread(read.thread, { preserveUpdatedAt: true })
    const readTurns = Array.isArray(read.thread.turns) ? read.thread.turns : []
    const hydratedTurns = readTurns.length > 0 ? readTurns : await listTurnsForHydrate(threadId, isCurrent)
    if (!isCurrent()) {
      traceSessionRuntime('hydrate aborted after turns list: stale scope', {
        threadId,
      })
      return
    }
    dependencies.setThreadTurns(threadId, hydratedTurns, { mode: 'replace' })

    hydratedThreadIds.add(threadId)
    traceSessionRuntime('hydrate applied', {
      threadId,
      turns: hydratedTurns.length,
      mode: 'replace',
    })
  }

  const ensureThreadReady = async (threadId: string, options?: EnsureThreadReadyOptions): Promise<void> => {
    if (!ensureStillCurrent(options?.isCurrent)) {
      return
    }

    const snapshot = dependencies.getThreadState()
    const cachedThread = snapshot.threadsById[threadId]
    const needsResume = !cachedThread || cachedThread.status?.type === 'notLoaded'
    if (needsResume) {
      traceSessionRuntime('ensure thread resume requested', {
        threadId,
      })
      const resumed = await api.resumeThread(threadId, {})
      if (!ensureStillCurrent(options?.isCurrent)) {
        traceSessionRuntime('ensure thread resume aborted: stale scope', {
          threadId,
        })
        return
      }
      dependencies.upsertThread(resumed.thread, { preserveUpdatedAt: true })
      traceSessionRuntime('ensure thread resume accepted', {
        threadId,
        status: resumed.thread.status?.type ?? null,
      })
    }

    await hydrateThreadState(threadId, {
      force: Boolean(options?.forceHydrate),
      isCurrent: options?.isCurrent,
    })
  }

  const loadModels = async (): Promise<void> => {
    const guard = buildGuard('loadModels')
    if (!guard.isCurrent()) {
      return
    }

    dependencies.setIsModelLoading(true)
    try {
      let cursor: string | null = null
      const nextOptions: ComposerModelOption[] = []
      const seen = new Set<string>()

      for (let page = 0; page < 5; page += 1) {
        const listed = await api.listModels({
          cursor,
          limit: 100,
          includeHidden: false,
        })
        if (!guard.isCurrent()) {
          return
        }
        for (const entry of listed.data) {
          const normalized = normalizeModelOption(entry)
          if (!normalized || seen.has(normalized.value)) {
            continue
          }
          seen.add(normalized.value)
          nextOptions.push(normalized)
        }
        if (!listed.nextCursor) {
          break
        }
        cursor = listed.nextCursor
      }

      if (!guard.isCurrent()) {
        return
      }

      nextOptions.sort((left, right) => {
        if (left.isDefault !== right.isDefault) {
          return left.isDefault ? -1 : 1
        }
        return left.label.localeCompare(right.label)
      })
      dependencies.setModelOptions(nextOptions)
    } catch {
      if (!guard.isCurrent()) {
        return
      }
      dependencies.setModelOptions([])
    } finally {
      if (guard.isCurrent()) {
        dependencies.setIsModelLoading(false)
      }
    }
  }

  const pollPendingRequests = async (options?: { surfaceErrors?: boolean }): Promise<void> => {
    const guard = buildGuard('pollPending')
    try {
      const pending = await api.listPendingRequests()
      if (!guard.isCurrent()) {
        return
      }
      dependencies.hydratePendingRequests(pending.data)
      dependencies.setLastPendingPollAtMs(Date.now())
    } catch (error) {
      if (!guard.isCurrent()) {
        return
      }
      if (options?.surfaceErrors !== false) {
        const message = error instanceof Error ? error.message : String(error)
        dependencies.setRuntimeError(message)
      }
    }
  }

  const selectThread = async (threadId: string | null): Promise<void> => {
    const scope = buildGuard('selectThread')
    if (!scope.isCurrent()) {
      return
    }

    traceSessionRuntime('select thread requested', {
      threadId,
    })

    const intent = selectionIntent + 1
    selectionIntent = intent
    scopeTokens.hydrateThread += 1
    const isCurrent = () => scope.isCurrent() && selectionIntent === intent

    if (threadId === null) {
      dependencies.setActiveThreadId(null)
      dependencies.setRuntimeError(null)
      traceSessionRuntime('select thread cleared', {})
      return
    }

    const snapshot = dependencies.getThreadState()
    if (snapshot.activeThreadId !== threadId) {
      dependencies.setActiveThreadId(threadId)
      traceSessionRuntime('select thread active set', {
        threadId,
      })
    }

    try {
      await ensureThreadReady(threadId, {
        isCurrent,
        // Always rehydrate on explicit selection so the transcript shown on screen
        // is guaranteed to come from the selected thread's latest server snapshot.
        forceHydrate: true,
      })
      if (!isCurrent()) {
        traceSessionRuntime('select thread aborted after ensure: stale scope', {
          threadId,
        })
        return
      }
      dependencies.setRuntimeError(null)
      traceSessionRuntime('select thread ready', {
        threadId,
      })
    } catch (error) {
      if (!isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
      traceSessionRuntime('select thread failed', {
        threadId,
        message,
      })
    }
  }

  const createThread = async (policy?: ThreadCreationPolicy): Promise<void> => {
    const scope = buildGuard('selectThread')
    const intent = selectionIntent + 1
    selectionIntent = intent
    const isCurrent = () => scope.isCurrent() && selectionIntent === intent

    try {
      const created = await api.startThread(policy ?? {})
      if (!isCurrent()) {
        return
      }
      dependencies.upsertThread(created.thread)
      await ensureThreadReady(created.thread.id, { isCurrent })
      if (!isCurrent()) {
        return
      }
      dependencies.setActiveThreadId(created.thread.id)
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const forkThread = async (threadId: string): Promise<void> => {
    const scope = buildGuard('selectThread')
    const intent = selectionIntent + 1
    selectionIntent = intent
    const isCurrent = () => scope.isCurrent() && selectionIntent === intent

    try {
      const forked = await api.forkThread(threadId, {})
      if (!isCurrent()) {
        return
      }
      dependencies.upsertThread(forked.thread)
      await ensureThreadReady(forked.thread.id, { isCurrent })
      if (!isCurrent()) {
        return
      }
      dependencies.setActiveThreadId(forked.thread.id)
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const refreshThreads = async (): Promise<void> => {
    const scope = buildGuard('selectThread')
    try {
      const listed = await api.listThreads({ limit: 50 })
      if (!scope.isCurrent()) {
        return
      }
      dependencies.setThreadList(listed.data)
      const activeThreadId = dependencies.getThreadState().activeThreadId
      if (activeThreadId) {
        await hydrateThreadState(activeThreadId, {
          force: true,
          isCurrent: scope.isCurrent,
        })
      }
      if (!scope.isCurrent()) {
        return
      }
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!scope.isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const actionFromSubmit = (
    runtime: RuntimeSnapshot,
    payload: ComposerSubmitPayload,
    policy?: TurnExecutionPolicy,
    context?: Extract<SessionInputAction, { type: 'turn.start' }>['context'],
  ): SessionInputAction | null => {
    const activeThreadId = runtime.activeThreadId
    if (!activeThreadId) {
      return null
    }

    if (runtime.activeRunningTurn) {
      return {
        type: 'turn.steer',
        threadId: activeThreadId,
        turnId: runtime.activeRunningTurn.id,
        input: payload.input,
      }
    }

    return {
      type: 'turn.start',
      threadId: activeThreadId,
      input: payload.input,
      policy: resolveTurnStartPolicy(policy, payload, runtime.selectedModel),
      context,
    }
  }

  const actionFromInterrupt = (runtime: RuntimeSnapshot): SessionInputAction | null => {
    const activeThreadId = runtime.activeThreadId
    const activeRunningTurn = runtime.activeRunningTurn
    if (!activeThreadId || !activeRunningTurn) {
      return null
    }

    return {
      type: 'turn.interrupt',
      threadId: activeThreadId,
      turnId: activeRunningTurn.id,
    }
  }

  const updateTurnFromResponse = (threadId: string, turn: SessionTurn): void => {
    const existingTurns = dependencies.getThreadState().turnsByThread[threadId] ?? []
    const nextTurns = upsertTurnList(existingTurns, turn)
    dependencies.setThreadTurns(threadId, nextTurns)
    dependencies.markThreadActivity(threadId)
  }

  const startTurnFromAction = async (
    action: Extract<SessionInputAction, { type: 'turn.start' }>,
  ): Promise<void> => {
    const policyWithoutModel: TurnExecutionPolicy = { ...(action.policy ?? {}) }
    const model = nonEmptyString(policyWithoutModel.model)
    delete policyWithoutModel.model
    const request: TurnStartRequestV4 = {
      ...policyWithoutModel,
      input: action.input,
    }
    if (model) {
      request.model = model
    }
    if (action.context?.mcpContext) {
      request.mcpContext = action.context.mcpContext
    }

    const result = await api.startTurn(action.threadId, request)
    if (!isControllerAlive()) {
      return
    }
    updateTurnFromResponse(action.threadId, result.turn)
  }

  const steerTurnFromAction = async (
    action: Extract<SessionInputAction, { type: 'turn.steer' }>,
  ): Promise<void> => {
    const result = await api.steerTurn(action.threadId, action.turnId, {
      expectedTurnId: action.turnId,
      input: action.input,
    })
    if (!isControllerAlive()) {
      return
    }
    updateTurnFromResponse(action.threadId, result.turn)
  }

  const interruptTurnFromAction = async (
    action: Extract<SessionInputAction, { type: 'turn.interrupt' }>,
  ): Promise<void> => {
    await api.interruptTurn(action.threadId, action.turnId, {})
  }

  const resolveRequestFromAction = async (
    action: Extract<SessionInputAction, { type: 'request.resolve' }>,
  ): Promise<void> => {
    await api.resolvePendingRequest(action.requestId, {
      resolutionKey: action.resolutionKey,
      result: action.result,
    })
    if (!isControllerAlive()) {
      return
    }
    dependencies.markPendingRequestSubmitted(action.requestId)
  }

  const rejectRequestFromAction = async (
    action: Extract<SessionInputAction, { type: 'request.reject' }>,
  ): Promise<void> => {
    await api.rejectPendingRequest(action.requestId, {
      resolutionKey: action.resolutionKey,
      reason: action.reason ?? null,
    })
    if (!isControllerAlive()) {
      return
    }
    dependencies.markPendingRequestSubmitted(action.requestId)
  }

  const submitSessionAction = async (action: SessionInputAction): Promise<void> => {
    try {
      switch (action.type) {
        case 'turn.start':
          await startTurnFromAction(action)
          break
        case 'turn.steer':
          await steerTurnFromAction(action)
          break
        case 'turn.interrupt':
          await interruptTurnFromAction(action)
          break
        case 'request.resolve':
          await resolveRequestFromAction(action)
          break
        case 'request.reject':
          await rejectRequestFromAction(action)
          break
        default:
          assertNever(action)
      }
      if (!isControllerAlive()) {
        return
      }
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isControllerAlive()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const submit = async (
    payload: ComposerSubmitPayload,
    policy?: TurnExecutionPolicy,
    context?: Extract<SessionInputAction, { type: 'turn.start' }>['context'],
  ): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const action = actionFromSubmit(runtime, payload, policy, context)
    if (!action) {
      return
    }

    await submitSessionAction(action)
  }

  const interrupt = async (): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const action = actionFromInterrupt(runtime)
    if (!action) {
      return
    }

    await submitSessionAction(action)
  }

  const bootstrap = async (policy?: Partial<SessionBootstrapPolicy>): Promise<void> => {
    const guard = buildGuard('bootstrap')
    if (!guard.isCurrent()) {
      return
    }
    const bootstrapPolicy = resolveBootstrapPolicy(policy)
    const bootstrapIntent = selectionIntent

    dependencies.setIsBootstrapping(true)
    dependencies.setConnectionPhase('connecting')
    try {
      const initialized = await api.initializeSession()
      if (!guard.isCurrent()) {
        return
      }
      dependencies.setConnectionInitialized(
        initialized.connection.clientName ?? 'PlanningTree Session V2',
        initialized.connection.serverVersion ?? null,
      )
      void loadModels()

      const loaded = await api.listLoadedThreads({ limit: 20 })
      if (!guard.isCurrent()) {
        return
      }
      const loadedThreadId = loaded.data[0] ?? null

      const listed = await api.listThreads({ limit: 50 })
      if (!guard.isCurrent()) {
        return
      }
      dependencies.setThreadList(listed.data)

      let selectedThreadId: string | null = null
      if (bootstrapPolicy.autoSelectInitialThread) {
        selectedThreadId = loadedThreadId ?? listed.data[0]?.id ?? null
      }

      const canMutateSelection = selectionIntent === bootstrapIntent

      if (
        bootstrapPolicy.autoSelectInitialThread &&
        bootstrapPolicy.autoCreateThreadWhenEmpty &&
        !selectedThreadId &&
        canMutateSelection
      ) {
        const created = await api.startThread(bootstrapPolicy.threadCreationPolicy ?? {})
        if (!guard.isCurrent()) {
          return
        }
        dependencies.upsertThread(created.thread)
        selectedThreadId = created.thread.id
      }

      if (bootstrapPolicy.autoSelectInitialThread && selectedThreadId && selectionIntent === bootstrapIntent) {
        await ensureThreadReady(selectedThreadId, {
          isCurrent: () => guard.isCurrent() && selectionIntent === bootstrapIntent,
        })
        if (!guard.isCurrent() || selectionIntent !== bootstrapIntent) {
          return
        }
        dependencies.setActiveThreadId(selectedThreadId)
      }
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!guard.isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
      dependencies.setConnectionError({
        code: 'ERR_INTERNAL',
        message,
      })
    } finally {
      if (guard.isCurrent()) {
        dependencies.setIsBootstrapping(false)
      }
    }
  }

  return {
    bootstrap,
    hydrateThreadState,
    ensureThreadReady,
    loadModels,
    pollPendingRequests,
    selectThread,
    createThread,
    forkThread,
    refreshThreads,
    submitSessionAction,
    submit,
    interrupt,
    resetHydratedState() {
      hydratedThreadIds.clear()
      selectionIntent = 0
    },
    dispose() {
      disposed = true
      hydratedThreadIds.clear()
      selectionIntent += 1
      for (const scope of Object.keys(scopeTokens) as AsyncScope[]) {
        scopeTokens[scope] += 1
      }
    },
  }
}
