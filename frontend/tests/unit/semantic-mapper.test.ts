import { describe, expect, it } from 'vitest'
import type { ChatMessage } from '../../src/api/types'
import { mapMessageToSemanticBlocks } from '../../src/features/breadcrumb/semanticMapper'

function makeAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    message_id: 'msg-1',
    role: 'assistant',
    content: '',
    status: 'streaming',
    error: null,
    turn_id: 'turn-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('semanticMapper', () => {
  it('maps lifecycle items into summary, plan, tool, and error blocks', () => {
    const message = makeAssistantMessage({
      error: 'Missing API key',
      items: [
        {
          item_id: 'assistant_text',
          item_type: 'assistant_text',
          status: 'completed',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:01Z',
          last_payload: null,
          lifecycle: [
            { phase: 'delta', timestamp: '2026-01-01T00:00:00Z', text: 'Finished implementation.' },
          ],
        },
        {
          item_id: 'plan-1',
          item_type: 'plan_item',
          status: 'streaming',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: null,
          last_payload: null,
          lifecycle: [
            { phase: 'delta', timestamp: '2026-01-01T00:00:00Z', text: 'Run tests' },
          ],
        },
        {
          item_id: 'tool:cmd-1',
          item_type: 'tool_call',
          status: 'completed',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:02Z',
          last_payload: { output: 'ok' },
          lifecycle: [
            {
              phase: 'started',
              timestamp: '2026-01-01T00:00:00Z',
              payload: { tool_name: 'shell_command', arguments: { command: 'npm test' } },
            },
            {
              phase: 'completed',
              timestamp: '2026-01-01T00:00:02Z',
              payload: { output: 'ok', exit_code: 0 },
            },
          ],
        },
      ],
    })
    const blocks = mapMessageToSemanticBlocks(message)
    expect(blocks.some((block) => block.type === 'summary')).toBe(true)
    expect(blocks.some((block) => block.type === 'plan')).toBe(true)
    expect(blocks.some((block) => block.type === 'tool_action')).toBe(true)
    expect(blocks.some((block) => block.type === 'error_blocker')).toBe(true)
  })

  it('falls back to legacy parts when items are absent', () => {
    const message = makeAssistantMessage({
      parts: [
        { type: 'assistant_text', content: 'Legacy summary', is_streaming: false },
        { type: 'plan_item', item_id: 'p-1', content: 'Inspect repo', is_streaming: false, timestamp: '2026-01-01T00:00:00Z' },
      ],
    })
    const blocks = mapMessageToSemanticBlocks(message)
    expect(blocks.some((block) => block.type === 'summary')).toBe(true)
    expect(blocks.some((block) => block.type === 'plan')).toBe(true)
  })
})
