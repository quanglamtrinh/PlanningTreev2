export type CommandOutputTailCache = {
  itemKey: string
  normalizedOutput: string
  normalizedLines: string[]
}

function normalizeOutputText(outputText: string): string {
  return outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
}

function appendDeltaLines(previous: string[], delta: string): string[] {
  if (!delta) {
    return previous
  }
  if (previous.length === 0) {
    return delta.split('\n')
  }
  const deltaLines = delta.split('\n')
  if (deltaLines.length === 0) {
    return previous
  }
  const next = [...previous]
  next[next.length - 1] = `${next[next.length - 1]}${deltaLines[0]}`
  for (let index = 1; index < deltaLines.length; index += 1) {
    next.push(deltaLines[index])
  }
  return next
}

function trailingFromNormalizedLines(lines: string[], maxLines: number): string {
  if (lines.length <= maxLines) {
    return lines.join('\n')
  }
  return lines.slice(-maxLines).join('\n')
}

export function computeTrailingCommandOutput(
  outputText: string,
  maxLines: number,
): string {
  const normalizedOutput = normalizeOutputText(outputText)
  const normalizedLines = normalizedOutput.split('\n')
  if (normalizedLines.length <= maxLines) {
    return normalizedOutput
  }
  return trailingFromNormalizedLines(normalizedLines, maxLines)
}

export function computeTrailingCommandOutputIncremental({
  previous,
  itemKey,
  outputText,
  maxLines,
}: {
  previous: CommandOutputTailCache | null
  itemKey: string
  outputText: string
  maxLines: number
}): {
  cache: CommandOutputTailCache
  visibleOutput: string
  usedIncrementalAppend: boolean
  didRebuild: boolean
} {
  const normalizedOutput = normalizeOutputText(outputText)

  if (
    previous &&
    previous.itemKey === itemKey &&
    normalizedOutput.length >= previous.normalizedOutput.length &&
    normalizedOutput.startsWith(previous.normalizedOutput)
  ) {
    const delta = normalizedOutput.slice(previous.normalizedOutput.length)
    const normalizedLines = appendDeltaLines(previous.normalizedLines, delta)
    return {
      cache: {
        itemKey,
        normalizedOutput,
        normalizedLines,
      },
      visibleOutput: trailingFromNormalizedLines(normalizedLines, maxLines),
      usedIncrementalAppend: true,
      didRebuild: false,
    }
  }

  const normalizedLines = normalizedOutput.split('\n')
  return {
    cache: {
      itemKey,
      normalizedOutput,
      normalizedLines,
    },
    visibleOutput:
      normalizedLines.length <= maxLines
        ? normalizedOutput
        : trailingFromNormalizedLines(normalizedLines, maxLines),
    usedIncrementalAppend: false,
    didRebuild: true,
  }
}
