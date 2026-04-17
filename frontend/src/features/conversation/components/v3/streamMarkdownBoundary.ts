const SAFE_BOUNDARY_MIN_CHARS = 24

function countChar(text: string, target: string): number {
  let count = 0
  for (const char of text) {
    if (char === target) {
      count += 1
    }
  }
  return count
}

function hasUnclosedInlineCode(text: string): boolean {
  const escapedFiltered = text.replace(/\\`/g, '')
  return countChar(escapedFiltered, '`') % 2 !== 0
}

function hasUnclosedFencedCodeBlock(text: string): boolean {
  const fenceMatches = text.match(/```/g)
  const fenceCount = fenceMatches ? fenceMatches.length : 0
  return fenceCount % 2 !== 0
}

function hasDanglingMarkdownLink(text: string): boolean {
  const linkOpenBracket = text.lastIndexOf('[')
  const linkCloseBracket = text.lastIndexOf(']')
  const linkOpenParen = text.lastIndexOf('(')
  const linkCloseParen = text.lastIndexOf(')')

  const hasOpenBracket = linkOpenBracket > linkCloseBracket
  const hasOpenParen = linkOpenParen > linkCloseParen
  if (!hasOpenBracket && !hasOpenParen) {
    return false
  }

  const tail = text.slice(Math.max(linkOpenBracket, linkOpenParen, 0))
  const nearTail = tail.length <= 120
  return nearTail
}

function endsWithStableBoundary(text: string): boolean {
  if (!text) {
    return false
  }
  if (/\n\s*$/.test(text)) {
    return true
  }
  if (/[.!?]\s*$/.test(text)) {
    return true
  }
  if (/[:;]\s*$/.test(text)) {
    return true
  }
  return false
}

export function shouldStreamRenderPlainText(
  content: string,
  {
    isStreaming,
    minChars = SAFE_BOUNDARY_MIN_CHARS,
  }: {
    isStreaming: boolean
    minChars?: number
  },
): boolean {
  if (!isStreaming) {
    return false
  }
  const text = String(content ?? '')
  if (!text.trim()) {
    return false
  }
  if (text.length < Math.max(8, Math.floor(minChars))) {
    return true
  }
  if (hasUnclosedFencedCodeBlock(text)) {
    return true
  }
  if (hasUnclosedInlineCode(text)) {
    return true
  }
  if (hasDanglingMarkdownLink(text)) {
    return true
  }
  if (!endsWithStableBoundary(text)) {
    return true
  }
  return false
}

export { SAFE_BOUNDARY_MIN_CHARS }
