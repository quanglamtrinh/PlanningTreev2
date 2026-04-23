import {
  forkThreadV2,
  initializeSessionV2,
  interruptTurnV2,
  listLoadedThreadsV2,
  listModelsV2,
  listPendingRequestsV2,
  listThreadsV2,
  listThreadTurnsV2,
  readThreadV2,
  rejectPendingRequestV2,
  resolvePendingRequestV2,
  resumeThreadV2,
  startThreadV2,
  startTurnV2,
  steerTurnV2,
  type SessionModelEntryV2,
} from '../api/client'
import { type ComposerSubmitPayload } from '../components/ComposerPane'
import type { PendingServerRequest, SessionError, SessionThread, SessionTurn } from '../contracts'
import type { ThreadSessionStoreState } from '../store/threadSessionStore'

const FULL_ACCESS_APPROVAL_POLICY = 'never'
const FULL_ACCESS_SANDBOX_POLICY: Record<string, unknown> = { type: 'dangerFullAccess' }

type AsyncScope = 'bootstrap' | 'selectThread' | 'hydrateThread' | 'loadModels' | 'pollPending'

type AsyncScopeTokens = Record<AsyncScope, number>

export type ComposerModelOption = {
  value: string
  label: string
  isDefault: boolean
}

export type SessionBootstrapPolicy = {
  autoSelectInitialThread: boolean
  autoCreateThreadWhenEmpty: boolean
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
  activeRequest: PendingServerRequest | null
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
  upsertThread: (thread: SessionThread, options?: { preserveUpdatedAt?: boolean }) => void
  markThreadActivity: (threadId: string, updatedAt?: number) => void
  setActiveThreadId: (threadId: string | null) => void
  setThreadTurns: (threadId: string, turns: SessionTurn[]) => void
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
  pollPendingRequests: () => Promise<void>
  selectThread: (threadId: string | null) => Promise<void>
  createThread: () => Promise<void>
  forkThread: (threadId: string) => Promise<void>
  refreshThreads: () => Promise<void>
  submit: (payload: ComposerSubmitPayload) => Promise<void>
  interrupt: () => Promise<void>
  resolveRequest: (result: Record<string, unknown>) => Promise<void>
  rejectRequest: (reason?: string | null) => Promise<void>
  resetHydratedState: () => void
  dispose: () => void
}

function actionId(): string {
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
  const model = typeof entry.model === 'string' ? entry.model.trim() : ''
  if (!model) {
    return null
  }
  const displayName = typeof entry.displayName === 'string' ? entry.displayName.trim() : ''
  return {
    value: model,
    label: displayName || model,
    isDefault: Boolean(entry.isDefault),
  }
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
  }
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

  const hydrateThreadState = async (threadId: string, options?: HydrateOptions): Promise<void> => {
    if (!options?.force && hydratedThreadIds.has(threadId)) {
      return
    }

    const guard = buildGuard('hydrateThread')
    const isCurrent = () => guard.isCurrent() && ensureStillCurrent(options?.isCurrent)

    const read = await api.readThread(threadId, false)
    if (!isCurrent()) {
      return
    }
    dependencies.upsertThread(read.thread, { preserveUpdatedAt: true })

    const turns = await api.listThreadTurns(threadId, { limit: 200 })
    if (!isCurrent()) {
      return
    }
    dependencies.setThreadTurns(threadId, turns.data)
    hydratedThreadIds.add(threadId)
  }

  const ensureThreadReady = async (threadId: string, options?: EnsureThreadReadyOptions): Promise<void> => {
    if (!ensureStillCurrent(options?.isCurrent)) {
      return
    }

    const snapshot = dependencies.getThreadState()
    const cachedThread = snapshot.threadsById[threadId]
    const needsResume = !cachedThread || cachedThread.status?.type === 'notLoaded'
    if (needsResume) {
      const resumed = await api.resumeThread(threadId, {})
      if (!ensureStillCurrent(options?.isCurrent)) {
        return
      }
      dependencies.upsertThread(resumed.thread, { preserveUpdatedAt: true })
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

  const pollPendingRequests = async (): Promise<void> => {
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
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const selectThread = async (threadId: string | null): Promise<void> => {
    const scope = buildGuard('selectThread')
    if (!scope.isCurrent()) {
      return
    }

    const intent = selectionIntent + 1
    selectionIntent = intent
    scopeTokens.hydrateThread += 1
    const isCurrent = () => scope.isCurrent() && selectionIntent === intent

    if (threadId === null) {
      dependencies.setActiveThreadId(null)
      dependencies.setRuntimeError(null)
      return
    }

    const snapshot = dependencies.getThreadState()
    if (snapshot.activeThreadId === threadId) {
      dependencies.setRuntimeError(null)
      return
    }

    const cachedThread = snapshot.threadsById[threadId]
    if (hydratedThreadIds.has(threadId) && cachedThread?.status?.type !== 'notLoaded') {
      dependencies.setActiveThreadId(threadId)
      dependencies.setRuntimeError(null)
      return
    }

    try {
      await ensureThreadReady(threadId, { isCurrent })
      if (!isCurrent()) {
        return
      }
      dependencies.setActiveThreadId(threadId)
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isCurrent()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const createThread = async (): Promise<void> => {
    const scope = buildGuard('selectThread')
    const intent = selectionIntent + 1
    selectionIntent = intent
    const isCurrent = () => scope.isCurrent() && selectionIntent === intent

    try {
      const created = await api.startThread({ modelProvider: 'openai' })
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

  const submit = async (payload: ComposerSubmitPayload): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const activeThreadId = runtime.activeThreadId
    if (!activeThreadId) {
      return
    }

    try {
      if (runtime.activeRunningTurn) {
        const result = await api.steerTurn(activeThreadId, runtime.activeRunningTurn.id, {
          clientActionId: actionId(),
          expectedTurnId: runtime.activeRunningTurn.id,
          input: payload.input,
        })
        if (!isControllerAlive()) {
          return
        }
        const nextTurns = upsertTurnList(runtime.activeTurns, result.turn)
        dependencies.setThreadTurns(activeThreadId, nextTurns)
        dependencies.markThreadActivity(activeThreadId)
      } else {
        const permissionOverrides = payload.accessMode === 'full-access'
          ? { approvalPolicy: FULL_ACCESS_APPROVAL_POLICY, sandboxPolicy: FULL_ACCESS_SANDBOX_POLICY }
          : {}
        const result = await api.startTurn(activeThreadId, {
          clientActionId: actionId(),
          input: payload.input,
          model: payload.model ?? runtime.selectedModel,
          ...permissionOverrides,
        })
        if (!isControllerAlive()) {
          return
        }
        const nextTurns = upsertTurnList(runtime.activeTurns, result.turn)
        dependencies.setThreadTurns(activeThreadId, nextTurns)
        dependencies.markThreadActivity(activeThreadId)
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

  const interrupt = async (): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const activeThreadId = runtime.activeThreadId
    if (!activeThreadId || !runtime.activeRunningTurn) {
      return
    }

    try {
      await api.interruptTurn(activeThreadId, runtime.activeRunningTurn.id, {
        clientActionId: actionId(),
      })
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

  const resolveRequest = async (result: Record<string, unknown>): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const activeRequest = runtime.activeRequest
    if (!activeRequest) {
      return
    }

    try {
      await api.resolvePendingRequest(activeRequest.requestId, {
        resolutionKey: actionId(),
        result,
      })
      if (!isControllerAlive()) {
        return
      }
      dependencies.markPendingRequestSubmitted(activeRequest.requestId)
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isControllerAlive()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
  }

  const rejectRequest = async (reason?: string | null): Promise<void> => {
    const runtime = dependencies.getRuntimeSnapshot()
    const activeRequest = runtime.activeRequest
    if (!activeRequest) {
      return
    }

    try {
      await api.rejectPendingRequest(activeRequest.requestId, {
        resolutionKey: actionId(),
        reason: reason ?? null,
      })
      if (!isControllerAlive()) {
        return
      }
      dependencies.markPendingRequestSubmitted(activeRequest.requestId)
      dependencies.setRuntimeError(null)
    } catch (error) {
      if (!isControllerAlive()) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      dependencies.setRuntimeError(message)
    }
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
        const created = await api.startThread({ modelProvider: 'openai' })
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
    submit,
    interrupt,
    resolveRequest,
    rejectRequest,
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
