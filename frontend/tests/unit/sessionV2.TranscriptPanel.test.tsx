import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'

import type { SessionItem, SessionTurn, VisibleTranscriptRow } from '../../src/features/session_v2/contracts'
import { TranscriptPanel as TranscriptPanelComponent } from '../../src/features/session_v2/components/TranscriptPanel'

function baseTurn(items: SessionItem[], status: SessionTurn['status'] = 'completed'): SessionTurn {
  return {
    id: 'turn-1',
    threadId: 'thread-1',
    status,
    lastCodexStatus: status === 'inProgress' || status === 'waitingUserInput' ? 'inProgress' : 'completed',
    startedAtMs: 1,
    completedAtMs: 2,
    error: null,
    items,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

function isRawChatItem(item: SessionItem): boolean {
  return item.normalizedKind === 'userMessage' || item.normalizedKind === 'agentMessage' || item.kind === 'userMessage' || item.kind === 'agentMessage'
}

function isWorkflowContextItem(item: SessionItem): boolean {
  const payload = isRecord(item.payload) ? item.payload : {}
  const metadata = isRecord(payload.metadata) ? payload.metadata : {}
  return metadata.workflowContext === true
}

function isInternalItem(turn: SessionTurn, item: SessionItem): boolean {
  const payload = isRecord(item.payload) ? item.payload : {}
  const metadata = isRecord(payload.metadata) ? payload.metadata : {}
  return metadata.workflowInternal === true || (turn.metadata?.workflowInternal === true && isRawChatItem(item))
}

function visibleRowsFor(turns: SessionTurn[], itemsByTurn?: Record<string, SessionItem[]>): VisibleTranscriptRow[] {
  const rows: VisibleTranscriptRow[] = []
  for (const turn of turns) {
    const items = itemsByTurn?.[`${turn.threadId}:${turn.id}`] ?? turn.items
    for (const item of items) {
      if (isInternalItem(turn, item) || isWorkflowContextItem(item)) {
        continue
      }
      rows.push({
        turn,
        item: {
          ...item,
          visibility: item.visibility ?? 'user',
          renderAs: item.renderAs ?? 'chatBubble',
        },
      })
    }
  }
  return rows
}

type TranscriptPanelProps = ComponentProps<typeof TranscriptPanelComponent>

function TranscriptPanel(props: TranscriptPanelProps) {
  return (
    <TranscriptPanelComponent
      {...props}
      visibleRows={props.visibleRows ?? visibleRowsFor(props.turns, props.itemsByTurn)}
    />
  )
}

function expandWorkflowContext() {
  fireEvent.click(screen.getByRole('button', { name: /Context/i }))
}

describe('TranscriptPanel', () => {
  it('renders native ThreadItem agent message text', () => {
    const item: SessionItem = {
      id: 'item-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Rendered from payload.text',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByText('Rendered from payload.text')).toBeInTheDocument()
    expect(screen.queryByText('agentMessage')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reasoning summary/i })).not.toBeInTheDocument()
  })

  it('renders injected workflow context as a visible context card', () => {
    const item: SessionItem = {
      id: 'workflow-context-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        text: '<planning_tree_context>{"hidden":true}</planning_tree_context>',
        metadata: {
          workflowContext: true,
          packetKind: 'ask_planning_context',
          contextPayload: {
            artifactContext: {
              ancestorContext: [
                {
                  node: { node_id: 'root', hierarchical_number: '1', title: 'Parent Task' },
                  frame: { content: 'Parent frame content' },
                  clarify: {
                    questions: [{ question: 'Which path?', custom_answer: 'Use the selected child.' }],
                  },
                  split: {
                    children: [
                      { node_id: 'child', hierarchical_number: '1.1', title: 'Current Child', isCurrentPath: true },
                      { node_id: 'sibling', hierarchical_number: '1.2', title: 'Sibling Child', isCurrentPath: false },
                    ],
                  },
                },
              ],
              currentContext: {
                node: { node_id: 'child', hierarchical_number: '1.1', title: 'Current Child' },
                frame: { content: 'Current frame content' },
                spec: { content: 'Current spec content' },
              },
            },
          },
        },
      },
    }

    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expect(screen.getByText('Context')).toBeInTheDocument()
    expect(screen.queryByText('Parent frame content')).not.toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getByText('1 Parent Task')).toBeInTheDocument()
    expect(screen.getByText('Parent frame content')).toBeInTheDocument()
    expect(screen.getByText('Use the selected child.')).toBeInTheDocument()
    expect(screen.getByText('1.1 Current Child')).toBeInTheDocument()
    expect(screen.getByText('current task')).toBeInTheDocument()
    expect(screen.getByText('Current spec content')).toBeInTheDocument()
    expect(container.textContent).not.toContain('<planning_tree_context>')
    expect(screen.queryByText('Unknown Codex item')).not.toBeInTheDocument()
  })

  it('renders injected workflow context when hydrated only on turn items', () => {
    const contextItem: SessionItem = {
      id: 'workflow-context-hydrated',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        text: '<planning_tree_context>{"hidden":true}</planning_tree_context>',
        metadata: {
          workflowContext: true,
          packetKind: 'ask_planning_context',
          contextPayload: {
            artifactContext: {
              ancestorContext: [],
              currentContext: {
                node: { node_id: 'child', hierarchical_number: '1.1', title: 'Hydrated Child' },
                frame: { content: 'Hydrated frame content' },
              },
            },
          },
        },
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([])]}
        itemsByTurn={{}}
        workflowContextItem={contextItem}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expect(screen.queryByText('Hydrated frame content')).not.toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getAllByText('1.1 Hydrated Child').length).toBeGreaterThan(0)
    expect(screen.getByText('Hydrated frame content')).toBeInTheDocument()
  })

  it('renders canonical node workflow context without a selected thread', () => {
    const contextItem: SessionItem = {
      id: 'canonical-workflow-context',
      threadId: 'workflow-context:threadless',
      turnId: 'canonical-workflow-context-turn',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        metadata: {
          workflowContext: true,
          workflowContextSource: 'node',
          packetKind: 'execution_context',
          contextPayload: {
            artifactContext: {
              ancestorContext: [],
              currentContext: {
                node: { node_id: 'child', hierarchical_number: '1.1', title: 'Canonical Child' },
                frame: { content: 'Canonical frame content' },
              },
            },
          },
        },
      },
    }

    render(
      <TranscriptPanel
        threadId={null}
        turns={[]}
        itemsByTurn={{}}
        workflowContextItem={contextItem}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getAllByText('1.1 Canonical Child').length).toBeGreaterThan(0)
    expect(screen.getByText('Canonical frame content')).toBeInTheDocument()
  })

  it('renders legacy workflow context from injected XML text', () => {
    const packet = {
      kind: 'ask_planning_context',
      payload: {
        artifactContext: {
          ancestorContext: [],
          currentContext: {
            node: { node_id: 'child', hierarchical_number: '1.1', title: 'Legacy Child' },
            frame: { content: 'Legacy frame content' },
            spec: { content: 'Legacy spec content' },
          },
        },
      },
    }
    const item: SessionItem = {
      id: 'workflow-context-legacy',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        text: `<planning_tree_context kind="ask_planning_context">\n${JSON.stringify(packet)}\n</planning_tree_context>`,
        metadata: {
          workflowContext: true,
          packetKind: 'ask_planning_context',
        },
      },
    }

    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getAllByText('1.1 Legacy Child').length).toBeGreaterThan(0)
    expect(screen.getByText('current task')).toBeInTheDocument()
    expect(screen.getByText('Legacy spec content')).toBeInTheDocument()
    expect(container.textContent).not.toContain('<planning_tree_context')
  })

  it('renders workflow context from Codex message response item content', () => {
    const packet = {
      kind: 'execution_context',
      payload: {
        artifactContext: {
          ancestorContext: [],
          currentContext: {
            node: { node_id: 'child', hierarchical_number: '1.1', title: 'Codex Item Child' },
            frame: { content: 'Codex item frame content' },
          },
        },
      },
    }
    const item: SessionItem = {
      id: 'workflow-context-codex-message',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'message',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'message',
        role: 'developer',
        content: [
          {
            type: 'input_text',
            text: `<planning_tree_context kind="execution_context">\n${JSON.stringify(packet)}\n</planning_tree_context>`,
          },
        ],
        metadata: {
          workflowContext: true,
          packetKind: 'execution_context',
        },
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getAllByText('1.1 Codex Item Child').length).toBeGreaterThan(0)
    expect(screen.getByText('Codex item frame content')).toBeInTheDocument()
  })

  it('renders workflow context update payloads from nextContext wrappers', () => {
    const item: SessionItem = {
      id: 'workflow-context-update',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        text: '<planning_tree_context>{"kind":"context_update"}</planning_tree_context>',
        metadata: {
          workflowContext: true,
          packetKind: 'context_update',
          contextPayload: {
            nextContext: {
              payload: {
                artifactContext: {
                  ancestorContext: [],
                  currentContext: {
                    node: { node_id: 'child', hierarchical_number: '1.1', title: 'Updated Child' },
                    frame: { content: 'Updated frame content' },
                    spec: { content: 'Updated spec content' },
                  },
                },
              },
            },
          },
        },
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getAllByText('1.1 Updated Child').length).toBeGreaterThan(0)
    expect(screen.getByText('current task')).toBeInTheDocument()
    expect(screen.getByText('Updated spec content')).toBeInTheDocument()
  })

  it('renders current frame and spec from compact workflow context payloads', () => {
    const item: SessionItem = {
      id: 'workflow-context-compact',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'systemMessage',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'systemMessage',
        text: '<planning_tree_context>{"kind":"child_activation_context"}</planning_tree_context>',
        metadata: {
          workflowContext: true,
          packetKind: 'child_activation_context',
          contextPayload: {
            parentNode: { node_id: 'parent', hierarchical_number: '1', title: 'Parent Task' },
            taskContext: {
              parent_chain_prompts: ['Parent task frame fallback'],
            },
            node: { node_id: 'child', hierarchical_number: '1.1', title: 'Compact Child' },
            frame: { confirmedContent: 'Compact frame content' },
            spec: { confirmedContent: 'Compact spec content' },
          },
        },
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByTestId('workflow-context-card')).toBeInTheDocument()
    expandWorkflowContext()
    expect(screen.getByText('1 Parent Task')).toBeInTheDocument()
    expect(screen.getByText('Parent task frame fallback')).toBeInTheDocument()
    expect(screen.getByText('1.1 Compact Child')).toBeInTheDocument()
    expect(screen.getByText('current task')).toBeInTheDocument()
    expect(screen.getByText('Compact frame content')).toBeInTheDocument()
    expect(screen.getByText('Compact spec content')).toBeInTheDocument()
  })

  it('renders delta-only payload while streaming', () => {
    const item: SessionItem = {
      id: 'item-2',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'inProgress',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        itemId: 'item-2',
        delta: 'Streaming delta text',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item], 'inProgress')]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByText('Streaming delta text')).toBeInTheDocument()
  })

  it('hides internal workflow artifact generation turns', () => {
    const internalItem: SessionItem = {
      id: 'item-internal',
      threadId: 'thread-1',
      turnId: 'turn-internal',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Hidden generated frame payload',
      },
    }
    const visibleItem: SessionItem = {
      id: 'item-visible',
      threadId: 'thread-1',
      turnId: 'turn-visible',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 2,
      updatedAtMs: 2,
      payload: {
        type: 'agentMessage',
        text: 'Visible Ask reply',
      },
    }
    const internalTurn: SessionTurn = {
      ...baseTurn([internalItem]),
      id: 'turn-internal',
      metadata: {
        workflowInternal: true,
        artifactKind: 'frame',
      },
    }
    const visibleTurn = {
      ...baseTurn([visibleItem]),
      id: 'turn-visible',
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[internalTurn, visibleTurn]}
        itemsByTurn={{
          'thread-1:turn-internal': [internalItem],
          'thread-1:turn-visible': [visibleItem],
        }}
      />,
    )

    expect(screen.queryByText('Hidden generated frame payload')).not.toBeInTheDocument()
    expect(screen.getByText('Visible Ask reply')).toBeInTheDocument()
  })

  it('hides internal workflow artifact generation items when turn metadata is missing', () => {
    const internalItem: SessionItem = {
      id: 'item-internal',
      threadId: 'thread-1',
      turnId: 'turn-internal',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: '{"questions":[{"question":"Hidden JSON"}]}',
        metadata: {
          workflowInternal: true,
          artifactKind: 'clarify',
        },
      },
    }
    const visibleItem: SessionItem = {
      id: 'item-visible',
      threadId: 'thread-1',
      turnId: 'turn-visible',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 2,
      updatedAtMs: 2,
      payload: {
        type: 'agentMessage',
        text: 'Visible Ask reply',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[
          { ...baseTurn([internalItem]), id: 'turn-internal' },
          { ...baseTurn([visibleItem]), id: 'turn-visible' },
        ]}
        itemsByTurn={{
          'thread-1:turn-internal': [internalItem],
          'thread-1:turn-visible': [visibleItem],
        }}
      />,
    )

    expect(screen.queryByText('{"questions":[{"question":"Hidden JSON"}]}')).not.toBeInTheDocument()
    expect(screen.getByText('Visible Ask reply')).toBeInTheDocument()
  })

  it('renders unknown native item as an explicit fallback card', () => {
    const item: SessionItem = {
      id: 'item-unknown',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'browserScreenshot',
      normalizedKind: null,
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        imageUrl: 'https://example.test/screenshot.png',
        width: 1280,
      },
    }

    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByText('Unknown Codex item')).toBeInTheDocument()
    const text = container.textContent ?? ''
    expect(text).toContain('kind: browserScreenshot')
    expect(text).toContain('payload:')
    expect(text).toContain('https://example.test/screenshot.png')
  })

  it('summarizes tool items when turn is terminal', () => {
    const message: SessionItem = {
      id: 'item-msg',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Done.',
      },
    }
    const command1: SessionItem = {
      id: 'item-cmd-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'ls',
      },
    }
    const command2: SessionItem = {
      id: 'item-cmd-2',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'pwd',
      },
    }

    const items = [message, command1, command2]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('Done.')).toBeInTheDocument()
    expect(screen.getByText('Ran 2 commands')).toBeInTheDocument()
    expect(screen.queryByText('commandExecution')).not.toBeInTheDocument()
  })

  it('keeps final summaries out of reasoning summary and expands work timeline in original order', () => {
    const messageA: SessionItem = {
      id: 'item-msg-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step A',
      },
    }
    const command1: SessionItem = {
      id: 'item-cmd-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'echo 1',
      },
    }
    const command2: SessionItem = {
      id: 'item-cmd-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'echo 2',
      },
    }
    const messageB: SessionItem = {
      id: 'item-msg-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step B',
      },
    }
    const fileChange: SessionItem = {
      id: 'item-file',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [{ kind: 'edit', path: 'src/app.ts' }],
      },
    }
    const messageC: SessionItem = {
      id: 'item-msg-c',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step C',
      },
    }

    const items = [messageA, command1, command2, messageB, fileChange, messageC]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    const reasoningSummaryToggle = screen.getByRole('button', { name: /Reasoning summary/i })
    expect(reasoningSummaryToggle).toBeInTheDocument()
    expect(screen.getByText('Step C')).toBeInTheDocument()
    expect(screen.queryByText('Step A')).not.toBeInTheDocument()
    expect(screen.queryByText('Step B')).not.toBeInTheDocument()
    expect(screen.queryByText('Ran 2 commands')).not.toBeInTheDocument()
    expect(screen.queryByText('Edited 1 file')).not.toBeInTheDocument()

    const allText = container.textContent ?? ''
    const posReasoningSummary = allText.indexOf('Reasoning summary')
    const posFileSummary = allText.indexOf('1 file changed')
    const posMessageC = allText.indexOf('Step C')

    expect(posReasoningSummary).toBeGreaterThanOrEqual(0)
    expect(posMessageC).toBeGreaterThan(posReasoningSummary)
    expect(posFileSummary).toBeGreaterThan(posMessageC)

    fireEvent.click(reasoningSummaryToggle)
    expect(screen.queryByText('Step A')).not.toBeInTheDocument()
    expect(screen.queryByText('Step B')).not.toBeInTheDocument()
    expect(screen.getByText('Ran 2 commands')).toBeInTheDocument()
    expect(screen.getByText('Edited 1 file')).toBeInTheDocument()

    const expandedText = container.textContent ?? ''
    const posExpandedRan = expandedText.indexOf('Ran 2 commands')
    const posExpandedEdited = expandedText.indexOf('Edited 1 file')
    const posExpandedStepC = expandedText.indexOf('Step C')
    expect(posExpandedRan).toBeGreaterThanOrEqual(0)
    expect(posExpandedEdited).toBeGreaterThan(posExpandedRan)
    expect(posExpandedStepC).toBeGreaterThan(posExpandedEdited)
  })

  it('keeps duplicate terminal assistant summary outside expanded reasoning summary', () => {
    const duplicateSummary: SessionItem = {
      id: 'item-summary-duplicate',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      normalizedKind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Final conclusion summary',
      },
    }
    const reasoning: SessionItem = {
      id: 'item-reasoning',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'reasoning',
      normalizedKind: 'reasoning',
      status: 'completed',
      createdAtMs: 2,
      updatedAtMs: 2,
      payload: {
        type: 'reasoning',
        summary: ['Checked constraints'],
        content: ['Compared options'],
      },
    }
    const finalSummary: SessionItem = {
      id: 'item-summary-final',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      normalizedKind: 'agentMessage',
      status: 'completed',
      createdAtMs: 3,
      updatedAtMs: 3,
      payload: {
        type: 'agentMessage',
        text: 'Final conclusion summary',
      },
    }

    const items = [duplicateSummary, reasoning, finalSummary]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('Final conclusion summary')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Reasoning summary/i }))
    const expandedText = container.textContent ?? ''
    expect(expandedText).toContain('Checked constraints')
    expect(expandedText).toContain('Compared options')
    expect(expandedText.match(/Final conclusion summary/g)).toHaveLength(1)
  })

  it('renders context compaction marker instead of raw tool payload', () => {
    const before: SessionItem = {
      id: 'item-before',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Before compact',
      },
    }
    const compact: SessionItem = {
      id: 'item-compact',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'error',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'contextCompaction',
      },
    }
    const after: SessionItem = {
      id: 'item-after',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'After compact',
      },
    }

    const items = [before, compact, after]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    const reasoningSummaryToggle = screen.getByRole('button', { name: /Reasoning summary/i })
    fireEvent.click(reasoningSummaryToggle)
    expect(screen.getByText('Context automatically compacted')).toBeInTheDocument()
    expect(screen.queryByText('contextCompaction')).not.toBeInTheDocument()
  })

  it('renders end-of-turn files changed summary card', () => {
    const message: SessionItem = {
      id: 'item-msg',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Applied patches',
      },
    }
    const fileChangeA: SessionItem = {
      id: 'item-file-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [
          {
            path: 'frontend/src/a.ts',
            kind: 'modify',
            diff: ['@@', '-old line', '+new line', '+newer line'].join('\n'),
          },
        ],
      },
    }
    const fileChangeB: SessionItem = {
      id: 'item-file-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [
          {
            path: 'frontend/src/b.ts',
            kind: 'delete',
            diff: ['@@', '-gone'].join('\n'),
          },
        ],
      },
    }

    const items = [message, fileChangeA, fileChangeB]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('2 files changed')).toBeInTheDocument()
    expect(screen.getByText('frontend/src/a.ts')).toBeInTheDocument()
    expect(screen.getByText('frontend/src/b.ts')).toBeInTheDocument()
    const allText = container.textContent ?? ''
    expect(allText).toContain('+2')
    expect(allText).toContain('-2')
    expect(allText.indexOf('Applied patches')).toBeLessThan(allText.indexOf('2 files changed'))
  })

  it('keeps hydrated file changes when live replay only has terminal message items', () => {
    const message: SessionItem = {
      id: 'item-msg',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 2,
      updatedAtMs: 2,
      payload: {
        type: 'agentMessage',
        text: 'Finished implementation',
      },
    }
    const fileChange: SessionItem = {
      id: 'item-file',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [
          {
            path: 'src/GameSurface.tsx',
            kind: 'add',
            diff: ['@@', '+export function GameSurface() {}'].join('\n'),
          },
        ],
      },
    }

    const items = [fileChange, message]
    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([], 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('Finished implementation')).toBeInTheDocument()
    expect(screen.getByText('1 file changed')).toBeInTheDocument()
    expect(screen.getByText('src/GameSurface.tsx')).toBeInTheDocument()
  })

  it('summarizes tool lines while turn is running', () => {
    const command: SessionItem = {
      id: 'item-cmd-running',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'inProgress',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'npm test',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([command], 'inProgress')]}
        itemsByTurn={{ 'thread-1:turn-1': [command] }}
      />,
    )

    expect(screen.getByText('Ran npm test')).toBeInTheDocument()
    expect(screen.queryByText('commandExecution')).not.toBeInTheDocument()
  })

  it('collapses long user message and toggles show more/show less', () => {
    const longText = Array.from({ length: 20 }, (_, index) => `line-${index + 1}`).join('\n')
    const userItem: SessionItem = {
      id: 'item-user-long',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'userMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'userMessage',
        text: longText,
      },
    }

    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([userItem], 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': [userItem] }}
      />,
    )

    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument()
    expect(container.textContent ?? '').not.toContain('line-20')

    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument()
    expect(container.textContent ?? '').toContain('line-20')
  })

  it('renders user message detail row with copy action', () => {
    const userItem: SessionItem = {
      id: 'item-user-detail',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'userMessage',
      status: 'completed',
      createdAtMs: Date.now(),
      updatedAtMs: Date.now(),
      payload: {
        type: 'userMessage',
        text: 'copy me',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([userItem], 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': [userItem] }}
      />,
    )

    expect(screen.getByLabelText('User message details')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy message' })).toBeInTheDocument()
  })

  it('does not render raw workflow context text when structured payload is unavailable', () => {
    const contextItem: SessionItem = {
      id: 'item-context',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Context packet that should be hidden',
        metadata: {
          workflowContext: true,
          role: 'execution',
        },
      },
    }
    const normalItem: SessionItem = {
      id: 'item-visible',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 2,
      updatedAtMs: 2,
      payload: {
        type: 'agentMessage',
        text: 'Visible assistant message',
      },
    }

    const items = [contextItem, normalItem]
    const { queryByText, getByText } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )
    expect(queryByText('Context packet that should be hidden')).not.toBeInTheDocument()
    expect(getByText('Visible assistant message')).toBeInTheDocument()
    expect(queryByText('Unknown Codex item')).not.toBeInTheDocument()
  })
})
