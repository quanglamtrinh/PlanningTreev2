import type { WorkflowContextPacketV2 } from '../workflow_v2/api/client'
import { formatNodeTitleWithIndex } from '../../utils/nodeDisplayIndex'

export const CONTEXT_DOC_RELATIVE_PATH = 'context.md'
export const CONTEXT_DOC_EMPTY_MARKDOWN = `# Context

No workflow context is available for this thread yet.
`

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function nodeTitle(node: unknown): string {
  if (!isRecord(node)) {
    return 'Untitled node'
  }
  return formatNodeTitleWithIndex({
    hierarchical_number: normalizeText(node.hierarchical_number),
    is_init_node: node.is_init_node === true,
    node_kind: normalizeText(node.node_kind),
    title: normalizeText(node.title),
    node_id: normalizeText(node.node_id),
  })
}

function documentContent(document: unknown): string {
  if (!isRecord(document)) {
    return ''
  }
  return typeof document.content === 'string' ? document.content.trim() : ''
}

function clarifyQuestions(clarify: unknown): Record<string, unknown>[] {
  if (!isRecord(clarify) || !Array.isArray(clarify.questions)) {
    return []
  }
  return clarify.questions.filter((question): question is Record<string, unknown> => isRecord(question))
}

function clarifyAnswerText(question: Record<string, unknown>): string {
  const selectedOptionId =
    normalizeText(question.selected_option_id) ||
    normalizeText(question.selectedOptionId) ||
    normalizeText(question.selectedOption)
  if (selectedOptionId && Array.isArray(question.options)) {
    const selectedOption = question.options.find(
      (option): option is Record<string, unknown> =>
        isRecord(option) && normalizeText(option.id) === selectedOptionId,
    )
    const selectedLabel =
      normalizeText(selectedOption?.label) ||
      normalizeText(selectedOption?.value) ||
      normalizeText(selectedOption?.id)
    if (selectedLabel) {
      return selectedLabel
    }
  }
  return (
    normalizeText(question.answer) ||
    normalizeText(question.custom_answer) ||
    normalizeText(question.customAnswer) ||
    normalizeText(question.value) ||
    'Not answered'
  )
}

function splitChildren(split: unknown): Record<string, unknown>[] {
  if (!isRecord(split) || !Array.isArray(split.children)) {
    return []
  }
  return split.children.filter((child): child is Record<string, unknown> => isRecord(child))
}

function artifactContextFromPayload(contextPayload: Record<string, unknown>): Record<string, unknown> {
  if (isRecord(contextPayload.artifactContext)) {
    return contextPayload.artifactContext
  }
  const taskContext = isRecord(contextPayload.taskContext) ? contextPayload.taskContext : null
  const parentPrompts = Array.isArray(taskContext?.parent_chain_prompts)
    ? taskContext.parent_chain_prompts.filter(
        (prompt): prompt is string => typeof prompt === 'string' && prompt.trim().length > 0,
      )
    : []
  const parentNode = isRecord(contextPayload.parentNode) ? contextPayload.parentNode : null
  const currentFrame = isRecord(contextPayload.frame) ? contextPayload.frame : null
  const currentSpec = isRecord(contextPayload.spec) ? contextPayload.spec : null
  const currentNode = isRecord(contextPayload.node) ? contextPayload.node : null
  if (parentPrompts.length > 0 || currentFrame || currentSpec || currentNode) {
    return {
      ancestorContext: parentPrompts.map((prompt, index) => ({
        node: index === parentPrompts.length - 1 && parentNode ? parentNode : { title: `Parent ${index + 1}` },
        summary: prompt,
        frame: { content: prompt },
        clarify: { questions: [] },
        split: { children: [] },
      })),
      currentContext: {
        node: currentNode,
        frame: currentFrame
          ? {
              ...currentFrame,
              content: normalizeText(currentFrame.confirmedContent) || normalizeText(currentFrame.content),
            }
          : null,
        spec: currentSpec
          ? {
              ...currentSpec,
              content: normalizeText(currentSpec.confirmedContent) || normalizeText(currentSpec.content),
            }
          : null,
      },
    }
  }
  return {}
}

function buildNodeSection(entry: Record<string, unknown>, isCurrent?: boolean): string | null {
  const frameText = documentContent(entry.frame)
  const specText = documentContent(entry.spec)
  const questions = clarifyQuestions(entry.clarify)
  const children = splitChildren(entry.split)
  const hasContent = Boolean(frameText || specText || questions.length > 0 || children.length > 0)
  if (!hasContent) {
    return null
  }

  const chunks: string[] = []
  chunks.push(`## ${nodeTitle(entry.node)}${isCurrent ? ' (current task)' : ''}`)
  if (frameText) {
    chunks.push('### frame.md')
    chunks.push(frameText)
  }
  if (specText) {
    chunks.push('### spec.md')
    chunks.push(specText)
  }
  if (questions.length > 0) {
    chunks.push('### Clarify')
    chunks.push(
      questions
        .map((question) => {
          const prompt = normalizeText(question.question) || normalizeText(question.field_name) || 'Question'
          return `- **${prompt}**: ${clarifyAnswerText(question)}`
        })
        .join('\n'),
    )
  }
  if (children.length > 0) {
    chunks.push('### Split')
    chunks.push(
      children
        .map((child) => `- ${nodeTitle(child)}${child.isCurrentPath === true ? ' (current path)' : ''}`)
        .join('\n'),
    )
  }
  return chunks.join('\n\n')
}

export function buildWorkflowContextMarkdown(packet: WorkflowContextPacketV2): string {
  const contextPayload = isRecord(packet.contextPayload) ? packet.contextPayload : {}
  const artifactContext = artifactContextFromPayload(contextPayload)
  const ancestorContext = Array.isArray(artifactContext.ancestorContext)
    ? artifactContext.ancestorContext.filter(isRecord)
    : []
  const currentContext = isRecord(artifactContext.currentContext) ? artifactContext.currentContext : null

  const sections: string[] = []
  for (const entry of ancestorContext) {
    const section = buildNodeSection(entry)
    if (section) {
      sections.push(section)
    }
  }
  if (currentContext) {
    const current = buildNodeSection(currentContext, true)
    if (current) {
      sections.push(current)
    }
  }

  if (sections.length === 0) {
    return CONTEXT_DOC_EMPTY_MARKDOWN
  }
  return `${sections.join('\n\n')}\n`
}
