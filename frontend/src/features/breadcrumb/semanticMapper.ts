import type { ChatMessage, MessageItem, MessagePart } from '../../api/types'

export type SemanticPlanStep = {
  id: string
  text: string
  status: 'active' | 'completed'
}

export type SemanticBlock =
  | { type: 'summary'; text: string; isStreaming: boolean }
  | { type: 'plan'; steps: SemanticPlanStep[] }
  | {
      type: 'tool_action'
      id: string
      name: string
      target: string | null
      status: 'running' | 'completed' | 'error'
      durationMs: number | null
      output: string | null
      exitCode: number | null
      payload: Record<string, unknown> | null
    }
  | {
      type: 'error_blocker'
      title: string
      impact: string
      attempted: string
      requiredDecision: string | null
    }

function concatenateItemText(item: MessageItem): string {
  return item.lifecycle
    .map((entry) => (typeof entry.text === 'string' ? entry.text : ''))
    .join('')
    .trim()
}

function startedPayload(item: MessageItem): Record<string, unknown> | null {
  const started = item.lifecycle.find((entry) => entry.phase === 'started')
  if (started?.payload && typeof started.payload === 'object') {
    return started.payload
  }
  if (item.last_payload && typeof item.last_payload === 'object') {
    return item.last_payload
  }
  return null
}

function completedPayload(item: MessageItem): Record<string, unknown> | null {
  const completed = [...item.lifecycle]
    .reverse()
    .find((entry) => entry.phase === 'completed' || entry.phase === 'error')
  if (completed?.payload && typeof completed.payload === 'object') {
    return completed.payload
  }
  return null
}

function mapItemsToBlocks(items: MessageItem[]): SemanticBlock[] {
  const blocks: SemanticBlock[] = []

  const textItem = items.find((item) => item.item_type === 'assistant_text')
  const summaryText = textItem ? concatenateItemText(textItem) : ''
  if (summaryText) {
    blocks.push({
      type: 'summary',
      text: summaryText,
      isStreaming: textItem?.status === 'streaming',
    })
  }

  const planItems = items.filter((item) => item.item_type === 'plan_item')
  if (planItems.length > 0) {
    const steps = planItems
      .map((item) => ({
        id: item.item_id,
        text: concatenateItemText(item),
        status: item.status === 'streaming' ? 'active' as const : 'completed' as const,
      }))
      .filter((step) => step.text.length > 0)
    if (steps.length > 0) {
      blocks.push({ type: 'plan', steps })
    }
  }

  const toolItems = items.filter((item) => item.item_type === 'tool_call')
  for (const item of toolItems) {
    const start = startedPayload(item)
    const end = completedPayload(item)
    const name = typeof start?.tool_name === 'string' ? start.tool_name : 'tool_action'
    const args =
      start?.arguments && typeof start.arguments === 'object'
        ? (start.arguments as Record<string, unknown>)
        : null
    const target = typeof args?.command === 'string'
      ? args.command
      : (typeof args?.path === 'string' ? args.path : null)
    const output = typeof end?.output === 'string' ? end.output : null
    const exitCode = typeof end?.exit_code === 'number' ? end.exit_code : null
    const startedAt = Date.parse(item.started_at)
    const completedAt = item.completed_at ? Date.parse(item.completed_at) : NaN
    const durationMs =
      Number.isFinite(startedAt) && Number.isFinite(completedAt)
        ? Math.max(0, completedAt - startedAt)
        : null
    blocks.push({
      type: 'tool_action',
      id: item.item_id,
      name,
      target,
      status: item.status === 'error' ? 'error' : item.status === 'completed' ? 'completed' : 'running',
      durationMs,
      output,
      exitCode,
      payload: args,
    })
  }

  const hasErrorItem = items.some((item) => item.status === 'error')
  if (hasErrorItem) {
    blocks.push({
      type: 'error_blocker',
      title: 'Agent encountered an execution blocker',
      impact: 'At least one lifecycle item failed during this turn.',
      attempted: 'The agent streamed intermediate progress before this error.',
      requiredDecision: 'Review error details and decide whether to retry.',
    })
  }

  return blocks
}

function mapPartsFallback(parts: MessagePart[] | undefined): SemanticBlock[] {
  const blocks: SemanticBlock[] = []
  const source = parts ?? []
  const text = source
    .filter((part): part is Extract<MessagePart, { type: 'assistant_text' }> => part.type === 'assistant_text')
    .map((part) => part.content)
    .join('')
    .trim()
  if (text) {
    blocks.push({ type: 'summary', text, isStreaming: source.some((p) => p.type === 'assistant_text' && p.is_streaming) })
  }
  const planSteps = source
    .filter((part): part is Extract<MessagePart, { type: 'plan_item' }> => part.type === 'plan_item')
    .map((part) => ({
      id: part.item_id,
      text: part.content.trim(),
      status: part.is_streaming ? 'active' as const : 'completed' as const,
    }))
    .filter((step) => step.text.length > 0)
  if (planSteps.length > 0) {
    blocks.push({ type: 'plan', steps: planSteps })
  }
  for (const [index, part] of source.entries()) {
    if (part.type !== 'tool_call') continue
    const target = typeof part.arguments.command === 'string'
      ? part.arguments.command
      : (typeof part.arguments.path === 'string' ? part.arguments.path : null)
    blocks.push({
      type: 'tool_action',
      id: part.call_id ?? `${part.tool_name}:${index}`,
      name: part.tool_name,
      target,
      status: part.status === 'error' ? 'error' : part.status === 'completed' ? 'completed' : 'running',
      durationMs: null,
      output: part.output ?? null,
      exitCode: part.exit_code ?? null,
      payload: part.arguments,
    })
  }
  return blocks
}

export function mapMessageToSemanticBlocks(message: ChatMessage): SemanticBlock[] {
  const itemBlocks = message.items && message.items.length > 0 ? mapItemsToBlocks(message.items) : []
  const baseBlocks = itemBlocks.length > 0 ? itemBlocks : mapPartsFallback(message.parts)
  if (!baseBlocks.some((block) => block.type === 'summary') && message.content.trim()) {
    baseBlocks.unshift({
      type: 'summary',
      text: message.content,
      isStreaming: message.status === 'streaming',
    })
  }
  if (message.error) {
    baseBlocks.push({
      type: 'error_blocker',
      title: 'Agent failed to complete this turn',
      impact: message.error,
      attempted: 'The turn was stopped before final completion.',
      requiredDecision: 'Provide guidance or retry the task.',
    })
  }
  return baseBlocks
}
