import type { ToolItem } from '../../../api/types'

function normalizeText(value: string | null | undefined): string {
  return String(value ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
}

export function cleanCommandText(commandText: string | null | undefined): string {
  const trimmed = normalizeText(commandText)
  if (!trimmed) {
    return ''
  }
  return trimmed.replace(/^Command:\s*/i, '').trim()
}

export function getToolHeadline(item: ToolItem): string {
  if (item.toolType === 'commandExecution') {
    const commandText = cleanCommandText(item.argumentsText || item.title || item.toolName)
    return commandText || 'Running command'
  }

  if (item.toolType === 'fileChange') {
    const title = normalizeText(item.title)
    if (title) {
      return title
    }
    if (item.outputFiles.length > 0) {
      return item.outputFiles.length === 1 ? item.outputFiles[0].path : `${item.outputFiles[0].path} +${item.outputFiles.length - 1}`
    }
    return 'Updating files'
  }

  return normalizeText(item.title) || normalizeText(item.toolName) || 'Tool activity'
}

export function getToolPlaceholderText(item: ToolItem): string {
  if (item.toolType === 'commandExecution') {
    return item.status === 'completed'
      ? 'Command finished without visible output.'
      : 'Waiting for command output...'
  }
  if (item.toolType === 'fileChange') {
    return item.status === 'completed' ? 'File changes completed.' : 'Preparing file changes...'
  }
  return item.status === 'completed' ? 'Tool completed.' : 'Waiting for tool output...'
}

export function hasMeaningfulToolContent(item: ToolItem): boolean {
  return (
    normalizeText(item.argumentsText).length > 0 ||
    normalizeText(item.outputText).length > 0 ||
    item.outputFiles.length > 0
  )
}
