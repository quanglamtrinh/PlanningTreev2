/// <reference lib="webworker" />

import {
  PHASE11_DIFF_WORKER_SCHEMA_VERSION,
  type Phase11DiffChunk,
  type Phase11DiffWorkerRequest,
  type Phase11DiffWorkerResponse,
} from './phase11DiffWorkerProtocol'

const STRUCTURED_DIFF_MARKER_RE =
  /^(?:diff --git |\+\+\+|---|@@ |\*\*\* Begin Patch|\*\*\* Update File:|\*\*\* Add File:|\*\*\* Delete File:|\*\*\* Move to:)/m

function hasStructuredDiffMarkers(text: string): boolean {
  return STRUCTURED_DIFF_MARKER_RE.test(text.replace(/\r\n/g, '\n').replace(/\r/g, '\n'))
}

function diffStatsFromText(text: string): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const line of text.split('\n')) {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      added += 1
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      removed += 1
    }
  }
  return { added, removed }
}

function resolvedDiffStatsFromText(text: string): { added: number; removed: number; known: boolean } {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const stats = diffStatsFromText(normalized)
  const hasEvidence =
    normalized.trim().length > 0 &&
    (stats.added > 0 || stats.removed > 0 || hasStructuredDiffMarkers(normalized))
  return {
    ...stats,
    known: hasEvidence,
  }
}

function stripGitABPrefix(segment: string): string {
  let normalized = segment.trim()
  if ((normalized.startsWith('a/') || normalized.startsWith('b/')) && normalized.length > 2) {
    normalized = normalized.slice(2)
  }
  return normalized.replace(/\\/g, '/')
}

function extractPathsFromDiffGitLine(line: string): string[] {
  const payload = line.slice('diff --git '.length).trimEnd()
  if (!payload) {
    return []
  }
  const paths: string[] = []
  let rest = payload
  while (rest.length > 0) {
    if (rest[0] === '"') {
      const end = rest.indexOf('"', 1)
      if (end < 0) {
        break
      }
      const raw = rest.slice(1, end)
      paths.push(stripGitABPrefix(raw))
      rest = rest.slice(end + 1).trimStart()
      continue
    }
    const whitespaceIndex = rest.indexOf(' ')
    const token = whitespaceIndex >= 0 ? rest.slice(0, whitespaceIndex) : rest
    paths.push(stripGitABPrefix(token))
    rest = whitespaceIndex >= 0 ? rest.slice(whitespaceIndex + 1).trimStart() : ''
  }
  return paths.filter(Boolean)
}

function isApplyPatchFileHeader(line: string): boolean {
  return (
    line.startsWith('*** Update File: ') ||
    line.startsWith('*** Add File: ') ||
    line.startsWith('*** Delete File: ')
  )
}

function extractApplyPatchPath(line: string): string | null {
  const match = line.match(/^\*\*\*\s+(?:Update File|Add File|Delete File|Move to):\s+(.+)$/)
  if (!match?.[1]) {
    return null
  }
  const raw = stripGitABPrefix(match[1].trim())
  return raw || null
}

function parseUnifiedDiffChunks(outputText: string): Phase11DiffChunk[] {
  const normalized = outputText.replace(/\r\n/g, '\n')
  if (!normalized.trim()) {
    return []
  }
  const lines = normalized.split('\n')
  const chunks: Phase11DiffChunk[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (line.startsWith('diff --git ')) {
      const startLine = index
      const relPaths = extractPathsFromDiffGitLine(line)
      index += 1
      let added = 0
      let removed = 0
      while (
        index < lines.length &&
        !lines[index].startsWith('diff --git ') &&
        !isApplyPatchFileHeader(lines[index])
      ) {
        const currentLine = lines[index]
        if (currentLine.startsWith('+') && !currentLine.startsWith('+++')) {
          added += 1
        } else if (currentLine.startsWith('-') && !currentLine.startsWith('---')) {
          removed += 1
        }
        index += 1
      }
      chunks.push({
        relPaths,
        added,
        removed,
        startLine,
        endLine: index,
      })
      continue
    }

    if (isApplyPatchFileHeader(line)) {
      const startLine = index
      const relPaths: string[] = []
      const path = extractApplyPatchPath(line)
      if (path) {
        relPaths.push(path)
      }
      index += 1
      let added = 0
      let removed = 0
      while (
        index < lines.length &&
        !lines[index].startsWith('diff --git ') &&
        !isApplyPatchFileHeader(lines[index])
      ) {
        const currentLine = lines[index]
        if (currentLine.startsWith('*** End Patch')) {
          break
        }
        if (currentLine.startsWith('*** Move to: ')) {
          const movePath = extractApplyPatchPath(currentLine)
          if (movePath) {
            relPaths.push(movePath)
          }
          index += 1
          continue
        }
        if (currentLine.startsWith('+') && !currentLine.startsWith('+++')) {
          added += 1
        } else if (currentLine.startsWith('-') && !currentLine.startsWith('---')) {
          removed += 1
        }
        index += 1
      }
      chunks.push({
        relPaths,
        added,
        removed,
        startLine,
        endLine: index,
      })
      continue
    }

    index += 1
  }

  return chunks
}

function splitLinesNormalized(text: string): string[] {
  if (!text.trim()) {
    return []
  }
  return text.split('\n')
}

const workerScope: DedicatedWorkerGlobalScope = self as unknown as DedicatedWorkerGlobalScope

workerScope.onmessage = (event: MessageEvent<unknown>) => {
  const startedAt = performance.now()
  const request = event.data as Partial<Phase11DiffWorkerRequest>

  if (!request || typeof request !== 'object') {
    return
  }

  const responseBase: Omit<Phase11DiffWorkerResponse, 'ok' | 'artifact' | 'error' | 'durationMs'> = {
    schemaVersion: PHASE11_DIFF_WORKER_SCHEMA_VERSION,
    jobId: String(request.jobId ?? ''),
    mode: request.mode === 'diff_artifacts_v1' ? request.mode : 'diff_artifacts_v1',
    requestSeq:
      typeof request.requestSeq === 'number' && Number.isFinite(request.requestSeq)
        ? Math.max(0, Math.floor(request.requestSeq))
        : 0,
  }

  if (
    request.schemaVersion !== PHASE11_DIFF_WORKER_SCHEMA_VERSION ||
    !responseBase.jobId ||
    request.mode !== 'diff_artifacts_v1'
  ) {
    workerScope.postMessage({
      ...responseBase,
      ok: false,
      artifact: null,
      error: 'worker_request_invalid',
      durationMs: Math.max(0, performance.now() - startedAt),
    } satisfies Phase11DiffWorkerResponse)
    return
  }

  try {
    const payload = request.payload as
      | Phase11DiffWorkerRequest['payload']
      | undefined
    const blobSourceText = String(payload?.blobSourceText ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const sourceText = String(payload?.sourceText ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const singleBodyText = String(payload?.singleBodyText ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')

    const artifact = {
      unifiedDiffChunks: parseUnifiedDiffChunks(blobSourceText),
      unifiedBlobLines: splitLinesNormalized(blobSourceText),
      sourceDiffStats: resolvedDiffStatsFromText(sourceText),
      singleBodyLines: splitLinesNormalized(singleBodyText),
    }

    workerScope.postMessage({
      ...responseBase,
      ok: true,
      artifact,
      error: null,
      durationMs: Math.max(0, performance.now() - startedAt),
    } satisfies Phase11DiffWorkerResponse)
  } catch {
    workerScope.postMessage({
      ...responseBase,
      ok: false,
      artifact: null,
      error: 'worker_compute_failed',
      durationMs: Math.max(0, performance.now() - startedAt),
    } satisfies Phase11DiffWorkerResponse)
  }
}
