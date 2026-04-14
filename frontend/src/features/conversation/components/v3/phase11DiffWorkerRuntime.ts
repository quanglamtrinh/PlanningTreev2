import {
  PHASE11_DIFF_WORKER_SCHEMA_VERSION,
  type Phase11DiffWorkerRequest,
  type Phase11DiffWorkerResponse,
} from './phase11DiffWorkerProtocol'

type PendingJob = {
  resolve: (value: Phase11DiffWorkerResponse) => void
  timeoutId: ReturnType<typeof globalThis.setTimeout>
}

const pendingJobs = new Map<string, PendingJob>()
let sharedWorker: Worker | null = null
let workerUnsupported = false

function fallbackErrorResponse(
  request: Phase11DiffWorkerRequest,
  errorCode: string,
): Phase11DiffWorkerResponse {
  return {
    schemaVersion: PHASE11_DIFF_WORKER_SCHEMA_VERSION,
    jobId: request.jobId,
    mode: request.mode,
    requestSeq: request.requestSeq,
    ok: false,
    artifact: null,
    error: errorCode,
    durationMs: 0,
  }
}

function settlePendingJob(response: Phase11DiffWorkerResponse): void {
  const pending = pendingJobs.get(response.jobId)
  if (!pending) {
    return
  }
  globalThis.clearTimeout(pending.timeoutId)
  pendingJobs.delete(response.jobId)
  pending.resolve(response)
}

function onWorkerMessage(event: MessageEvent<unknown>): void {
  const payload = event.data as Partial<Phase11DiffWorkerResponse>
  if (!payload || typeof payload !== 'object') {
    return
  }
  if (payload.schemaVersion !== PHASE11_DIFF_WORKER_SCHEMA_VERSION) {
    return
  }
  if (typeof payload.jobId !== 'string' || !payload.jobId.trim()) {
    return
  }
  const response: Phase11DiffWorkerResponse = {
    schemaVersion: PHASE11_DIFF_WORKER_SCHEMA_VERSION,
    jobId: payload.jobId,
    mode: payload.mode === 'diff_artifacts_v1' ? payload.mode : 'diff_artifacts_v1',
    requestSeq:
      typeof payload.requestSeq === 'number' && Number.isFinite(payload.requestSeq)
        ? Math.max(0, Math.floor(payload.requestSeq))
        : 0,
    ok: payload.ok === true,
    artifact: payload.artifact ?? null,
    error: typeof payload.error === 'string' ? payload.error : null,
    durationMs:
      typeof payload.durationMs === 'number' && Number.isFinite(payload.durationMs)
        ? Math.max(0, payload.durationMs)
        : 0,
  }
  settlePendingJob(response)
}

function onWorkerError(event: ErrorEvent): void {
  const errorText = event.message?.trim() || 'worker_runtime_error'
  const pending = [...pendingJobs.entries()]
  for (const [jobId, job] of pending) {
    globalThis.clearTimeout(job.timeoutId)
    pendingJobs.delete(jobId)
    job.resolve({
      schemaVersion: PHASE11_DIFF_WORKER_SCHEMA_VERSION,
      jobId,
      mode: 'diff_artifacts_v1',
      requestSeq: 0,
      ok: false,
      artifact: null,
      error: errorText,
      durationMs: 0,
    })
  }
}

function ensureWorker(): Worker | null {
  if (workerUnsupported) {
    return null
  }
  if (sharedWorker) {
    return sharedWorker
  }
  if (typeof Worker === 'undefined') {
    workerUnsupported = true
    return null
  }
  try {
    const worker = new Worker(
      new URL('./phase11DiffWorker.ts', import.meta.url),
      { type: 'module' },
    )
    worker.onmessage = onWorkerMessage
    worker.onerror = onWorkerError
    sharedWorker = worker
    return worker
  } catch {
    workerUnsupported = true
    return null
  }
}

export async function runPhase11DiffWorkerJob({
  request,
  timeoutMs,
}: {
  request: Phase11DiffWorkerRequest
  timeoutMs: number
}): Promise<Phase11DiffWorkerResponse> {
  const worker = ensureWorker()
  if (!worker) {
    return fallbackErrorResponse(request, 'worker_unavailable')
  }
  const normalizedTimeoutMs =
    Number.isFinite(timeoutMs) && timeoutMs > 0 ? Math.floor(timeoutMs) : 1

  return await new Promise<Phase11DiffWorkerResponse>((resolve) => {
    const timeoutId = globalThis.setTimeout(() => {
      pendingJobs.delete(request.jobId)
      resolve(fallbackErrorResponse(request, 'worker_timeout'))
    }, normalizedTimeoutMs)

    pendingJobs.set(request.jobId, {
      resolve,
      timeoutId,
    })

    try {
      worker.postMessage(request)
    } catch {
      globalThis.clearTimeout(timeoutId)
      pendingJobs.delete(request.jobId)
      resolve(fallbackErrorResponse(request, 'worker_post_message_failed'))
    }
  })
}

export function resetPhase11DiffWorkerRuntimeForTests(): void {
  const pending = [...pendingJobs.entries()]
  for (const [jobId, job] of pending) {
    globalThis.clearTimeout(job.timeoutId)
    pendingJobs.delete(jobId)
    job.resolve({
      schemaVersion: PHASE11_DIFF_WORKER_SCHEMA_VERSION,
      jobId,
      mode: 'diff_artifacts_v1',
      requestSeq: 0,
      ok: false,
      artifact: null,
      error: 'worker_runtime_reset',
      durationMs: 0,
    })
  }
  if (sharedWorker) {
    sharedWorker.terminate()
    sharedWorker = null
  }
  workerUnsupported = false
}
