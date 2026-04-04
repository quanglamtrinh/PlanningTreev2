type InferredFileChangeType = 'created' | 'updated' | 'deleted'

export interface InferredFileWrite {
  path: string
  changeType: InferredFileChangeType
  summary: string | null
}

const POWERSHELL_WRITE_PATH_RE =
  /\b(?:Set-Content|Add-Content|Out-File)\b[\s\S]{0,200}?-(?:LiteralPath|Path)\s+(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([^\s|;]+))/gi
const SHELL_REDIRECT_RE =
  /(?:^|[;\s])(?:>|>>)\s*(?:"([^"\r\n]+)"|'([^'\r\n]+)'|([^\s|;]+))/gm
const PATCH_HEADER_PATH_RE = /^\*\*\*\s+(?:Add File|Update File|Delete File|Move to):\s+(.+)$/gm
const POWERSHELL_HERE_STRING_SINGLE_RE =
  /@'([\s\S]*?)'@\s*\|\s*(?:Set-Content|Add-Content|Out-File)\b/i
const POWERSHELL_HERE_STRING_DOUBLE_RE =
  /@"([\s\S]*?)"@\s*\|\s*(?:Set-Content|Add-Content|Out-File)\b/i
const POWERSHELL_VALUE_RE =
  /\b(?:Set-Content|Add-Content)\b[\s\S]{0,240}?-Value\s+(?:"([^"\r\n]+)"|'([^'\r\n]+)')/i

function sanitizePathCandidate(raw: string | null | undefined): string | null {
  let trimmed = String(raw ?? '').trim()
  if (!trimmed) {
    return null
  }
  trimmed = trimmed.replace(/^[`'"(\[]+/, '')
  trimmed = trimmed.replace(/[`'"),;\]]+$/, '')
  trimmed = trimmed.trim()
  if (!trimmed) {
    return null
  }
  if (trimmed.startsWith('-')) {
    return null
  }
  const lowered = trimmed.toLowerCase()
  if (lowered === '$null' || lowered === 'nul' || lowered === 'con') {
    return null
  }
  if (!/[\\/\.]/.test(trimmed)) {
    return null
  }
  if (trimmed.length > 400) {
    return null
  }
  return trimmed
}

function canonicalPathKey(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+/g, '/').toLowerCase()
}

function collectRegexMatches(
  source: string,
  regex: RegExp,
  collector: Set<string>,
  selectPath: (match: RegExpExecArray) => string | null,
): void {
  regex.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = regex.exec(source)) !== null) {
    const candidate = sanitizePathCandidate(selectPath(match))
    if (candidate) {
      collector.add(candidate)
    }
  }
}

export function inferFileWritesFromCommandText(
  commandText: string | null | undefined,
): InferredFileWrite[] {
  const source = String(commandText ?? '')
  if (!source.trim()) {
    return []
  }

  const paths = new Set<string>()

  collectRegexMatches(source, POWERSHELL_WRITE_PATH_RE, paths, (match) => {
    return match[1] ?? match[2] ?? match[3] ?? null
  })

  collectRegexMatches(source, SHELL_REDIRECT_RE, paths, (match) => {
    return match[1] ?? match[2] ?? match[3] ?? null
  })

  collectRegexMatches(source, PATCH_HEADER_PATH_RE, paths, (match) => {
    return match[1] ?? null
  })

  const uniquePathsByKey = new Map<string, string>()
  for (const path of paths) {
    const key = canonicalPathKey(path)
    if (!uniquePathsByKey.has(key)) {
      uniquePathsByKey.set(key, path)
    }
  }

  return [...uniquePathsByKey.values()].map((path) => ({
    path,
    changeType: 'updated',
    summary: 'Inferred from shell write command',
  }))
}

function normalizeInferredContent(content: string | null | undefined): string | null {
  const normalized = String(content ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const cleaned = normalized.trim()
  if (!cleaned) {
    return null
  }
  return cleaned
}

export function inferInlineFileWriteContentFromCommandText(
  commandText: string | null | undefined,
): string | null {
  const source = String(commandText ?? '')
  if (!source.trim()) {
    return null
  }

  const single = source.match(POWERSHELL_HERE_STRING_SINGLE_RE)
  if (single?.[1]) {
    return normalizeInferredContent(single[1])
  }

  const double = source.match(POWERSHELL_HERE_STRING_DOUBLE_RE)
  if (double?.[1]) {
    return normalizeInferredContent(double[1])
  }

  const valueMatch = source.match(POWERSHELL_VALUE_RE)
  if (valueMatch) {
    return normalizeInferredContent(valueMatch[1] ?? valueMatch[2] ?? '')
  }

  return null
}

export function toAddedDiffText(content: string | null | undefined): string {
  const normalized = String(content ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const trimmed = normalized.trim()
  if (!trimmed) {
    return ''
  }
  return trimmed
    .split('\n')
    .map((line) => `+${line}`)
    .join('\n')
}
