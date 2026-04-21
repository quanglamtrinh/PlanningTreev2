const HASH_LOCATION_SUFFIX_RE = /^L\d+(?:C\d+)?(?:-L\d+(?:C\d+)?)?$/
const COLON_LOCATION_SUFFIX_RE = /:\d+(?::\d+)?(?:[-\u2013]\d+(?::\d+)?)?$/
const URL_SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/

export type ParsedLocalLinkTarget = {
  normalizedPathText: string
  locationSuffix: string | null
}

function parseMarkdownHashLocationPoint(point: string): [string, string | null] | null {
  if (!point.startsWith('L')) {
    return null
  }
  const body = point.slice(1)
  if (!body) {
    return null
  }
  const splitIndex = body.indexOf('C')
  if (splitIndex === -1) {
    return /^\d+$/.test(body) ? [body, null] : null
  }
  const line = body.slice(0, splitIndex)
  const column = body.slice(splitIndex + 1)
  if (!/^\d+$/.test(line) || !/^\d+$/.test(column)) {
    return null
  }
  return [line, column]
}

export function normalizeMarkdownHashLocationSuffix(suffix: string): string | null {
  const fragment = suffix.startsWith('#') ? suffix.slice(1) : suffix
  if (!fragment) {
    return null
  }
  const [start, end] = fragment.includes('-')
    ? (() => {
        const [startPart, endPart] = fragment.split('-', 2)
        return [startPart, endPart] as const
      })()
    : [fragment, null]
  const startPoint = parseMarkdownHashLocationPoint(start)
  if (!startPoint) {
    return null
  }
  const [startLine, startColumn] = startPoint
  let normalized = `:${startLine}`
  if (startColumn) {
    normalized += `:${startColumn}`
  }
  if (end) {
    const endPoint = parseMarkdownHashLocationPoint(end)
    if (!endPoint) {
      return null
    }
    const [endLine, endColumn] = endPoint
    normalized += `-${endLine}`
    if (endColumn) {
      normalized += `:${endColumn}`
    }
  }
  return normalized
}

function normalizeHashLocationSuffixFragment(fragment: string): string | null {
  if (!HASH_LOCATION_SUFFIX_RE.test(fragment)) {
    return null
  }
  return normalizeMarkdownHashLocationSuffix(`#${fragment}`)
}

function extractColonLocationSuffix(pathText: string): string | null {
  const match = pathText.match(COLON_LOCATION_SUFFIX_RE)
  return match ? match[0] : null
}

function normalizeLocalLinkPathText(pathText: string): string {
  if (pathText.startsWith('\\\\')) {
    const rest = pathText.slice(2).replace(/\\/g, '/').replace(/^\/+/, '')
    return `//${rest}`
  }
  return pathText.replace(/\\/g, '/')
}

function isAbsoluteLocalLinkPath(pathText: string): boolean {
  return (
    pathText.startsWith('/') ||
    pathText.startsWith('//') ||
    /^[a-zA-Z]:\//.test(pathText)
  )
}

function trimTrailingLocalPathSeparator(pathText: string): string {
  if (pathText === '/' || pathText === '//') {
    return pathText
  }
  if (/^[a-zA-Z]:\/$/.test(pathText)) {
    return pathText
  }
  return pathText.replace(/\/+$/, '')
}

function stripLocalPathPrefix(pathText: string, rootText: string): string | null {
  const normalizedPath = trimTrailingLocalPathSeparator(pathText)
  const normalizedRoot = trimTrailingLocalPathSeparator(rootText)
  if (!normalizedPath || !normalizedRoot) {
    return null
  }
  if (normalizedPath === normalizedRoot) {
    return null
  }
  if (normalizedRoot === '/' || normalizedRoot === '//') {
    return normalizedPath.startsWith('/') ? normalizedPath.slice(1) : null
  }
  if (!normalizedPath.startsWith(normalizedRoot)) {
    return null
  }
  const remainder = normalizedPath.slice(normalizedRoot.length)
  if (!remainder.startsWith('/')) {
    return null
  }
  return remainder.slice(1)
}

function fileUrlToLocalPathText(url: URL): string | null {
  let pathText = decodeURIComponent(url.pathname || '')
  if (url.hostname && url.hostname !== 'localhost') {
    pathText = `//${url.hostname}${pathText}`
  } else if (/^\/[a-zA-Z]:\//.test(pathText)) {
    pathText = pathText.slice(1)
  }
  return normalizeLocalLinkPathText(pathText)
}

export function isLocalPathLikeLink(destination: string): boolean {
  const value = destination.trim()
  if (!value) {
    return false
  }
  if (
    value.startsWith('file://') ||
    value.startsWith('/') ||
    value.startsWith('~/') ||
    value.startsWith('./') ||
    value.startsWith('../') ||
    value.startsWith('\\\\') ||
    /^[a-zA-Z]:[\\/]/.test(value)
  ) {
    return true
  }
  if (value.startsWith('#')) {
    return false
  }
  if (URL_SCHEME_RE.test(value)) {
    return false
  }
  // Plain relative links like `docs/frame.md` are treated as local paths.
  return true
}

export function parseLocalLinkTarget(destination: string): ParsedLocalLinkTarget | null {
  if (!isLocalPathLikeLink(destination)) {
    return null
  }
  if (destination.startsWith('file://')) {
    let url: URL
    try {
      url = new URL(destination)
    } catch {
      return null
    }
    if (url.protocol !== 'file:') {
      return null
    }
    const normalizedPathText = fileUrlToLocalPathText(url)
    if (!normalizedPathText) {
      return null
    }
    const fragment = url.hash ? url.hash.slice(1) : ''
    const locationSuffix = fragment ? normalizeHashLocationSuffixFragment(fragment) : null
    return { normalizedPathText, locationSuffix }
  }

  let pathText = destination
  let locationSuffix: string | null = null

  const hashIndex = destination.lastIndexOf('#')
  if (hashIndex !== -1) {
    const candidatePath = destination.slice(0, hashIndex)
    const fragment = destination.slice(hashIndex + 1)
    const normalizedHash = normalizeHashLocationSuffixFragment(fragment)
    if (normalizedHash) {
      pathText = candidatePath
      locationSuffix = normalizedHash
    }
  }

  if (!locationSuffix) {
    const suffix = extractColonLocationSuffix(pathText)
    if (suffix) {
      pathText = pathText.slice(0, pathText.length - suffix.length)
      locationSuffix = suffix
    }
  }

  return {
    normalizedPathText: normalizeLocalLinkPathText(pathText),
    locationSuffix,
  }
}

function displayLocalLinkPath(pathText: string, projectRootPath?: string): string {
  const normalizedPath = normalizeLocalLinkPathText(pathText)
  if (!isAbsoluteLocalLinkPath(normalizedPath)) {
    return normalizedPath
  }
  if (!projectRootPath) {
    return normalizedPath
  }
  const normalizedRoot = normalizeLocalLinkPathText(projectRootPath)
  const stripped = stripLocalPathPrefix(normalizedPath, normalizedRoot)
  return stripped ?? normalizedPath
}

export function renderLocalLinkTarget(
  destination: string,
  { projectRootPath }: { projectRootPath?: string } = {},
): string | null {
  const parsed = parseLocalLinkTarget(destination)
  if (!parsed) {
    return null
  }
  const renderedPath = displayLocalLinkPath(parsed.normalizedPathText, projectRootPath)
  return parsed.locationSuffix ? `${renderedPath}${parsed.locationSuffix}` : renderedPath
}
