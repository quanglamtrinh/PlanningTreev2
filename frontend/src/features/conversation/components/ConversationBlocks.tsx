import type {
  ConversationApprovalRequestRenderItem,
  ConversationDiffSummaryRenderItem,
  ConversationFileChangeSummaryRenderItem,
  ConversationPlanBlockRenderItem,
  ConversationPlanStepUpdateRenderItem,
  ConversationReasoningRenderItem,
  ConversationRenderItem,
  ConversationStatusBlockRenderItem,
  ConversationUserInputRequestRenderItem,
  ConversationUserInputResponseRenderItem,
  ConversationToolCallRenderItem,
  ConversationToolResultRenderItem,
  ConversationUnsupportedRenderItem,
} from '../model/buildConversationRenderModel'
import { normalizeSplitPayload } from '../model/normalizeSplitPayload'
import styles from './ConversationSurface.module.css'

function renderMetaLine(label: string, value: string | null) {
  if (!value) {
    return null
  }

  return (
    <p className={styles.blockMetaLine}>
      <span className={styles.blockMetaLabel}>{label}</span> {value}
    </p>
  )
}

function renderSplitPayload(payload: Record<string, unknown> | null) {
  const normalized = normalizeSplitPayload(payload)
  if (!normalized) {
    return null
  }

  if (normalized.kind === 'unsupported') {
    return (
      <p className={styles.unsupportedFallback}>{normalized.message}</p>
    )
  }

  return (
    <div className={styles.blockGrid}>
      {normalized.cards.map((subtask) => (
        <article key={subtask.key} className={styles.blockCard}>
          <div className={styles.blockCardSection}>
            <h5 className={styles.blockCardTitle}>{subtask.title}</h5>
            {subtask.body ? <p className={styles.blockCardText}>{subtask.body}</p> : null}
            {subtask.meta.map((meta) => renderMetaLine(`${meta.label}:`, meta.value))}
          </div>
        </article>
      ))}
    </div>
  )
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function statsText(item: ConversationDiffSummaryRenderItem): string | null {
  const values = [
    item.stats.added !== null ? `+${item.stats.added}` : null,
    item.stats.removed !== null ? `-${item.stats.removed}` : null,
    item.stats.changed !== null ? `~${item.stats.changed}` : null,
  ].filter((value): value is string => Boolean(value))
  return values.length > 0 ? values.join(' ') : null
}

export function UnsupportedBlock({ item }: { item: ConversationUnsupportedRenderItem }) {
  return <div className={styles.unsupportedFallback}>Unsupported content: {item.partType}</div>
}

export function ReasoningBlock({ item }: { item: ConversationReasoningRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Reasoning</p>
      {item.title ? <h5 className={styles.blockTitle}>{item.title}</h5> : null}
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {item.text ? <p className={styles.blockText}>{item.text}</p> : null}
    </section>
  )
}

export function ToolCallBlock({ item }: { item: ConversationToolCallRenderItem }) {
  const splitPayload =
    item.toolName === 'emit_render_data' &&
    item.arguments &&
    typeof item.arguments.kind === 'string' &&
    item.arguments.kind === 'split_result' &&
    item.arguments.payload &&
    typeof item.arguments.payload === 'object' &&
    !Array.isArray(item.arguments.payload)
      ? (item.arguments.payload as Record<string, unknown>)
      : null

  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Tool Call</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.toolName ?? 'Tool call'}</h5>
        {item.toolCallId ? <span className={styles.blockTag}>{item.toolCallId}</span> : null}
      </div>
      {splitPayload ? (
        renderSplitPayload(splitPayload)
      ) : item.arguments ? (
        <pre className={styles.codeBlock}>{formatJson(item.arguments)}</pre>
      ) : null}
    </section>
  )
}

export function ToolResultBlock({ item }: { item: ConversationToolResultRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Tool Result</p>
      {item.toolCallId ? <p className={styles.blockSummary}>Result for {item.toolCallId}</p> : null}
      {item.text ? <p className={styles.blockText}>{item.text}</p> : null}
      {item.result !== null && item.result !== undefined ? (
        <pre className={styles.codeBlock}>{formatJson(item.result)}</pre>
      ) : null}
    </section>
  )
}

export function PlanBlock({ item }: { item: ConversationPlanBlockRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Plan</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.title ?? 'Plan snapshot'}</h5>
        {item.planId ? <span className={styles.blockTag}>{item.planId}</span> : null}
      </div>
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {item.text ? <p className={styles.blockText}>{item.text}</p> : null}
      {item.steps.length > 0 ? (
        <div className={styles.blockList}>
          {item.steps.map((step) => (
            <div key={step.key} className={styles.blockListItem}>
              <strong>{step.title ?? step.key}</strong>
              {step.status ? <span>{step.status}</span> : null}
              {step.description ? <span>{step.description}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export function PlanStepUpdateBlock({ item }: { item: ConversationPlanStepUpdateRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Plan Step</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.title ?? item.stepId ?? 'Step update'}</h5>
        {item.statusLabel ? <span className={styles.blockTag}>{item.statusLabel}</span> : null}
      </div>
      {item.text ? <p className={styles.blockText}>{item.text}</p> : null}
    </section>
  )
}

function renderInteractiveStateTag(label: string | null) {
  if (!label) {
    return null
  }
  return <span className={styles.blockTag}>{label}</span>
}

export function ApprovalRequestBlock({ item }: { item: ConversationApprovalRequestRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Approval Request</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.title ?? 'Approval needed'}</h5>
        {renderInteractiveStateTag(item.resolutionState)}
      </div>
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {item.prompt ? <p className={styles.blockText}>{item.prompt}</p> : null}
      {item.decision ? <p className={styles.blockMetaLine}>Decision: {item.decision}</p> : null}
    </section>
  )
}

export function UserInputRequestBlock({ item }: { item: ConversationUserInputRequestRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Runtime Input</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.title ?? 'Input requested'}</h5>
        {renderInteractiveStateTag(item.resolutionState)}
      </div>
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {item.prompt ? <p className={styles.blockText}>{item.prompt}</p> : null}
      {item.questions.length > 0 ? (
        <div className={styles.blockList}>
          {item.questions.map((question) => (
            <div key={question.key} className={styles.blockListItem}>
              <strong>{question.header ?? question.key}</strong>
              {question.question ? <span>{question.question}</span> : null}
              {question.options.length > 0 ? <span>Options: {question.options.join(', ')}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export function UserInputResponseBlock({ item }: { item: ConversationUserInputResponseRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Runtime Input Response</p>
      <h5 className={styles.blockTitle}>{item.title ?? 'Answer submitted'}</h5>
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {item.text ? <p className={styles.blockText}>{item.text}</p> : null}
      {item.answers.length > 0 ? (
        <div className={styles.blockList}>
          {item.answers.map((answer) => (
            <div key={answer.key} className={styles.blockListItem}>
              <strong>{answer.label}</strong>
              {answer.values.length > 0 ? <span>{answer.values.join(', ')}</span> : <span>(no answer text)</span>}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

export function DiffSummaryBlock({ item }: { item: ConversationDiffSummaryRenderItem }) {
  const stats = statsText(item)
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Diff Summary</p>
      {item.title ? <h5 className={styles.blockTitle}>{item.title}</h5> : null}
      {item.summary ? <p className={styles.blockSummary}>{item.summary}</p> : null}
      {stats ? <p className={styles.blockSummary}>{stats}</p> : null}
      {item.files.length > 0 ? (
        <ul className={styles.blockBullets}>
          {item.files.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

export function FileChangeSummaryBlock({ item }: { item: ConversationFileChangeSummaryRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>File Change</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.filePath ?? 'File change'}</h5>
        {item.changeType ? <span className={styles.blockTag}>{item.changeType}</span> : null}
      </div>
      {item.summary ? <p className={styles.blockText}>{item.summary}</p> : null}
    </section>
  )
}

export function StatusBlock({ item }: { item: ConversationStatusBlockRenderItem }) {
  return (
    <section className={styles.richBlock}>
      <p className={styles.blockKicker}>Status</p>
      <div className={styles.blockHeaderRow}>
        <h5 className={styles.blockTitle}>{item.title ?? 'Execution status'}</h5>
        {item.statusLabel ? <span className={styles.blockTag}>{item.statusLabel}</span> : null}
      </div>
      {item.summary ? <p className={styles.blockText}>{item.summary}</p> : null}
    </section>
  )
}

export function renderConversationBlock(item: ConversationRenderItem) {
  switch (item.kind) {
    case 'reasoning':
      return <ReasoningBlock item={item} />
    case 'tool_call':
      return <ToolCallBlock item={item} />
    case 'tool_result':
      return <ToolResultBlock item={item} />
    case 'plan_block':
      return <PlanBlock item={item} />
    case 'plan_step_update':
      return <PlanStepUpdateBlock item={item} />
    case 'approval_request':
      return <ApprovalRequestBlock item={item} />
    case 'user_input_request':
      return <UserInputRequestBlock item={item} />
    case 'user_input_response':
      return <UserInputResponseBlock item={item} />
    case 'diff_summary':
      return <DiffSummaryBlock item={item} />
    case 'file_change_summary':
      return <FileChangeSummaryBlock item={item} />
    case 'status_block':
      return <StatusBlock item={item} />
    case 'unsupported':
      return <UnsupportedBlock item={item} />
    default:
      return null
  }
}
