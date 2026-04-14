export const PHASE11_DIFF_WORKER_SCHEMA_VERSION = 1

export type Phase11DiffWorkerMode = 'diff_artifacts_v1'

export type Phase11DiffChunk = {
  relPaths: string[]
  added: number
  removed: number
  startLine: number
  endLine: number
}

export type Phase11ResolvedDiffStats = {
  added: number
  removed: number
  known: boolean
}

export type Phase11DiffArtifacts = {
  unifiedDiffChunks: Phase11DiffChunk[]
  unifiedBlobLines: string[]
  sourceDiffStats: Phase11ResolvedDiffStats
  singleBodyLines: string[]
}

export type Phase11DiffWorkerRequest = {
  schemaVersion: typeof PHASE11_DIFF_WORKER_SCHEMA_VERSION
  jobId: string
  threadId: string | null
  itemId: string
  updatedAt: string
  mode: Phase11DiffWorkerMode
  requestSeq: number
  payload: {
    blobSourceText: string
    sourceText: string
    singleBodyText: string
  }
}

export type Phase11DiffWorkerResponse = {
  schemaVersion: typeof PHASE11_DIFF_WORKER_SCHEMA_VERSION
  jobId: string
  mode: Phase11DiffWorkerMode
  requestSeq: number
  ok: boolean
  artifact: Phase11DiffArtifacts | null
  error: string | null
  durationMs: number
}
