import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'

import type { RuntimeInputAnswer } from '../../../api/types'
import type {
  ActiveConversationRequest,
  ConversationRequestQuestion,
} from '../hooks/useConversationRequests'
import { normalizeSplitPayload } from '../model/normalizeSplitPayload'
import type {
  ConversationApprovalRequestRenderItem,
  ConversationDiffSummaryRenderItem,
  ConversationFileChangeSummaryRenderItem,
  ConversationPlanBlockRenderItem,
  ConversationPlanStepUpdateRenderItem,
  ConversationReasoningRenderItem,
  ConversationRenderEntry,
  ConversationRenderItem,
  ConversationRenderMessage,
  ConversationStatusBlockRenderItem,
  ConversationTextRenderItem,
  ConversationToolCallRenderItem,
  ConversationToolResultRenderItem,
  ConversationUnsupportedRenderItem,
  ConversationUserInputRequestRenderItem,
  ConversationUserInputResponseRenderItem,
} from '../model/buildConversationRenderModel'
import { ConversationMarkdown } from './ConversationMarkdown'
import type {
  ConversationSurfaceMessageAction,
  ConversationSurfaceProps,
} from './ConversationSurface.types'
import styles from './ExecutionConversationSurface.module.css'

type Props = ConversationSurfaceProps
type RequestQuestionDrafts = Record<string, string>

const AUTO_FOLLOW_THRESHOLD_PX = 96

function formatConnectionLabel(value: Props['connectionState']): string {
  return value.replace(/_/g, ' ')
}

function TypingIndicator() {
  return (
    <span className={styles.typingIndicator} aria-label="Streaming response">
      <span />
      <span />
      <span />
    </span>
  )
}

function LoadingDots() {
  return (
    <div className={styles.loadingDots} aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  )
}

function Spinner() {
  return <span className={styles.spinner} aria-hidden="true" />
}

function formatDuration(durationMs: number | null | undefined): string | null {
  if (durationMs === null || durationMs === undefined || durationMs < 0) {
    return null
  }

  const totalSeconds = Math.max(0, Math.round(durationMs / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes}:${String(seconds).padStart(2, '0')}` : `${seconds}s`
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function copyToClipboard(value: string): Promise<void> {
  if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
    return Promise.reject(new Error('Clipboard is not available.'))
  }
  return navigator.clipboard.writeText(value)
}

function quoteMarkdown(value: string): string {
  return value
    .split(/\r?\n/)
    .map((line) => (line.length > 0 ? `> ${line}` : '>'))
    .join('\n')
}

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.clientHeight - element.scrollTop <= AUTO_FOLLOW_THRESHOLD_PX
}

function textLooksTerminal(text: string | null): boolean {
  if (!text) {
    return false
  }
  if (text.includes('\n')) {
    return true
  }
  return /(^[$>#]|^PS [A-Z]:\\|^\w+@[\w.-]+:)/m.test(text)
}

function extractCommandFromArguments(argumentsValue: Record<string, unknown> | null): string | null {
  if (!argumentsValue) {
    return null
  }
  return (
    asString(argumentsValue.command) ??
    asString(argumentsValue.cmd) ??
    asString(argumentsValue.script) ??
    null
  )
}

function extractSplitPayload(argumentsValue: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!argumentsValue || argumentsValue.kind !== 'split_result') {
    return null
  }
  return asRecord(argumentsValue.payload)
}

function readTerminalResultText(item: ConversationToolResultRenderItem): string | null {
  if (typeof item.result === 'string' && textLooksTerminal(item.result)) {
    return item.result
  }
  if (item.text && textLooksTerminal(item.text)) {
    return item.text
  }
  return null
}

function buildPassiveQuestions(
  item: ConversationUserInputRequestRenderItem,
): ConversationRequestQuestion[] {
  return item.questions.map((question) => ({
    id: question.key,
    header: question.header ?? question.key,
    question: question.question ?? '',
    isOther: question.options.length === 0,
    isSecret: false,
    options: question.options.map((label) => ({
      label,
      description: '',
    })),
  }))
}

function MarkdownText({
  value,
  className,
}: {
  value: string | null | undefined
  className?: string
}) {
  if (!value) {
    return null
  }
  return <ConversationMarkdown value={value} className={className} />
}

function StatusTag({
  value,
  tone = 'default',
}: {
  value: string | null | undefined
  tone?: 'default' | 'warning' | 'danger' | 'success'
}) {
  if (!value) {
    return null
  }

  const toneClass =
    tone === 'warning'
      ? styles.tagWarning
      : tone === 'danger'
        ? styles.tagDanger
        : tone === 'success'
          ? styles.tagSuccess
          : styles.tagDefault

  return <span className={`${styles.tag} ${toneClass}`}>{value}</span>
}

function RowCard({
  kicker,
  title,
  tag,
  tone = 'default',
  summary,
  children,
}: {
  kicker: string
  title?: string | null
  tag?: ReactNode
  tone?: 'default' | 'warning' | 'danger'
  summary?: string | null
  children?: ReactNode
}) {
  const toneClass =
    tone === 'warning'
      ? styles.cardWarning
      : tone === 'danger'
        ? styles.cardDanger
        : styles.cardDefault

  return (
    <section className={`${styles.card} ${toneClass}`}>
      <p className={styles.cardKicker}>{kicker}</p>
      {title || tag ? (
        <div className={styles.cardHeader}>
          {title ? <h5 className={styles.cardTitle}>{title}</h5> : null}
          {tag}
        </div>
      ) : null}
      <MarkdownText value={summary} className={styles.cardText} />
      {children}
    </section>
  )
}

function SplitPayload({ payload }: { payload: Record<string, unknown> }) {
  const normalized = normalizeSplitPayload(payload)
  if (!normalized) {
    return null
  }

  if (normalized.kind === 'unsupported') {
    return <div className={styles.unsupportedFallback}>{normalized.message}</div>
  }

  return (
    <div className={styles.splitGrid}>
      {normalized.cards.map((subtask) => (
        <article
          key={subtask.key}
          className={styles.splitCard}
        >
          <h6 className={styles.splitTitle}>{subtask.title}</h6>
          <MarkdownText value={subtask.body} className={styles.splitText} />
          {subtask.meta.map((meta) => (
            <p key={`${subtask.key}-${meta.label}`} className={styles.splitMeta}>
              <strong>{meta.label}:</strong> {meta.value}
            </p>
          ))}
        </article>
      ))}
    </div>
  )
}

function TerminalBlock({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className={styles.terminalBlock}>
      <div className={styles.terminalHeader}>{label}</div>
      <pre className={styles.terminalPre}>{value}</pre>
    </div>
  )
}

function TextItem({
  item,
  tone,
  onQuoteMessage,
}: {
  item: ConversationTextRenderItem
  tone: ConversationRenderMessage['roleTone']
  onQuoteMessage?: (quotedMarkdown: string) => void
}) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setCopied(false)
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function handleCopy() {
    try {
      await copyToClipboard(item.text)
      setCopied(true)
    } catch {
      return
    }
  }

  return (
    <div
      className={`${styles.textCard} ${
        tone === 'user' ? styles.userTextCard : styles.assistantTextCard
      }`}
    >
      <div className={styles.inlineActions}>
        <button
          type="button"
          className={styles.inlineActionButton}
          aria-label="Copy message"
          onClick={() => void handleCopy()}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        {onQuoteMessage ? (
          <button
            type="button"
            className={styles.inlineActionButton}
            aria-label="Quote message"
            onClick={() => onQuoteMessage(quoteMarkdown(item.text))}
          >
            Quote
          </button>
        ) : null}
      </div>
      <ConversationMarkdown value={item.text} className={styles.textMarkdown} />
    </div>
  )
}

function ReasoningItem({ item }: { item: ConversationReasoningRenderItem }) {
  return (
    <RowCard
      kicker="Reasoning"
      title={item.title ?? 'Working through the next step'}
      summary={item.summary}
      tone="warning"
    >
      <MarkdownText value={item.text} className={styles.cardText} />
    </RowCard>
  )
}

function ToolCallItem({ item }: { item: ConversationToolCallRenderItem }) {
  const splitPayload = extractSplitPayload(item.arguments)
  const command = extractCommandFromArguments(item.arguments)

  return (
    <RowCard
      kicker="Tool Call"
      title={item.toolName ?? 'Tool call'}
      tag={<StatusTag value={item.toolCallId} />}
    >
      {splitPayload ? <SplitPayload payload={splitPayload} /> : null}
      {!splitPayload && command ? <TerminalBlock label="Command" value={command} /> : null}
      {!splitPayload && !command && item.arguments ? (
        <TerminalBlock label="Arguments" value={formatJson(item.arguments)} />
      ) : null}
    </RowCard>
  )
}

function ToolResultItem({ item }: { item: ConversationToolResultRenderItem }) {
  const terminalText = readTerminalResultText(item)

  return (
    <RowCard
      kicker="Tool Result"
      title={item.toolCallId ? `Result for ${item.toolCallId}` : 'Tool output'}
      summary={!terminalText ? item.text : null}
    >
      {terminalText ? <TerminalBlock label="Output" value={terminalText} /> : null}
      {item.result !== null && item.result !== undefined && item.result !== terminalText ? (
        <TerminalBlock label="Payload" value={formatJson(item.result)} />
      ) : null}
    </RowCard>
  )
}

function PlanBlockItem({ item }: { item: ConversationPlanBlockRenderItem }) {
  return (
    <RowCard kicker="Plan" title={item.title ?? 'Plan snapshot'} tag={<StatusTag value={item.planId} />}>
      <MarkdownText value={item.summary} className={styles.cardText} />
      <MarkdownText value={item.text} className={styles.cardText} />
      {item.steps.length > 0 ? (
        <div className={styles.detailList}>
          {item.steps.map((step) => (
            <div key={step.key} className={styles.detailListItem}>
              <strong>{step.title ?? step.key}</strong>
              {step.status ? <span>{step.status}</span> : null}
              {step.description ? <span>{step.description}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </RowCard>
  )
}

function PlanStepUpdateItem({ item }: { item: ConversationPlanStepUpdateRenderItem }) {
  return (
    <RowCard
      kicker="Plan Step"
      title={item.title ?? item.stepId ?? 'Step update'}
      tag={<StatusTag value={item.statusLabel} />}
      summary={item.text}
    />
  )
}

function ApprovalRequestItem({
  item,
  activeRequest,
  requestUi,
}: {
  item: ConversationApprovalRequestRenderItem
  activeRequest: ActiveConversationRequest | null
  requestUi: Props['requestUi']
}) {
  const isActive =
    activeRequest?.requestKind === 'approval' && activeRequest.requestId === item.requestId

  return (
    <RowCard
      kicker="Approval Request"
      title={item.title ?? 'Approval needed'}
      tag={<StatusTag value={item.resolutionState} tone="warning" />}
      summary={item.summary}
      tone="warning"
    >
      <MarkdownText value={item.prompt} className={styles.cardText} />
      {item.decision ? <p className={styles.cardMeta}>Decision: {item.decision}</p> : null}
      <div className={styles.requestActions}>
        <button type="button" className={styles.requestActionButton} disabled aria-label="Approve request">
          Approve
        </button>
        <button type="button" className={styles.requestActionButton} disabled aria-label="Decline request">
          Decline
        </button>
      </div>
      {isActive ? (
        <p className={styles.requestHelp}>
          Approval requests are shown inline here, but this runtime still controls approval outside the
          chat action layer.
        </p>
      ) : null}
      {requestUi?.error && isActive ? <p className={styles.requestError}>{requestUi.error}</p> : null}
    </RowCard>
  )
}

function RuntimeInputQuestion({
  question,
  value,
  onChange,
}: {
  question: ConversationRequestQuestion
  value: string
  onChange: (nextValue: string) => void
}) {
  const options = question.options ?? []

  return (
    <article className={styles.questionCard}>
      <div className={styles.questionHeader}>
        <strong>{question.header}</strong>
        {question.isSecret ? <StatusTag value="private" /> : null}
      </div>
      <p className={styles.questionText}>{question.question}</p>
      {options.length > 0 ? (
        <div className={styles.optionList}>
          {options.map((option) => (
            <label key={option.label} className={styles.optionItem}>
              <input
                type="radio"
                name={question.id}
                checked={value === option.label}
                onChange={() => onChange(option.label)}
              />
              <span>
                <strong>{option.label}</strong>
                {option.description ? ` ${option.description}` : ''}
              </span>
            </label>
          ))}
        </div>
      ) : null}
      {question.isOther || options.length === 0 ? (
        <textarea
          className={styles.requestTextarea}
          rows={question.isSecret ? 2 : 3}
          value={value}
          placeholder={question.isSecret ? 'Enter your answer privately...' : 'Type your answer...'}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}
    </article>
  )
}

function RuntimeInputRequestItem({
  item,
  activeRequest,
  requestUi,
}: {
  item: ConversationUserInputRequestRenderItem
  activeRequest: ActiveConversationRequest | null
  requestUi: Props['requestUi']
}) {
  const resolvedQuestions =
    activeRequest?.requestKind === 'user_input' && activeRequest.requestId === item.requestId
      ? activeRequest.questions
      : buildPassiveQuestions(item)
  const isActive =
    activeRequest?.requestKind === 'user_input' && activeRequest.requestId === item.requestId
  const isSupersededPending =
    activeRequest?.requestKind === 'user_input' &&
    activeRequest.requestId !== item.requestId &&
    item.resolutionState === 'pending'
  const [drafts, setDrafts] = useState<RequestQuestionDrafts>({})

  useEffect(() => {
    if (!isActive || !activeRequest) {
      return
    }
    setDrafts((current) => {
      const next: RequestQuestionDrafts = {}
      for (const question of activeRequest.questions) {
        if (current[question.id]) {
          next[question.id] = current[question.id]
        }
      }
      return next
    })
  }, [activeRequest, isActive])

  const canSubmit =
    Boolean(isActive && requestUi) &&
    resolvedQuestions.length > 0 &&
    resolvedQuestions.every((question) => (drafts[question.id] ?? '').trim().length > 0) &&
    !requestUi?.isSubmitting

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!isActive || !requestUi || !canSubmit || !activeRequest) {
      return
    }

    const answers = Object.fromEntries(
      activeRequest.questions.map((question) => [
        question.id,
        {
          answers: [(drafts[question.id] ?? '').trim()],
        } satisfies RuntimeInputAnswer,
      ]),
    )

    try {
      await requestUi.submitUserInputResponse({
        requestId: activeRequest.requestId,
        threadId: activeRequest.threadId,
        turnId: activeRequest.turnId,
        answers,
      })
    } catch {
      return
    }
  }

  if (isSupersededPending) {
    return (
      <RowCard
        kicker="Runtime Input"
        title={item.title ?? 'Earlier request'}
        tag={<StatusTag value="replaced" />}
        summary="A newer runtime question replaced this earlier prompt."
      />
    )
  }

  return (
    <RowCard
      kicker="Runtime Input"
      title={item.title ?? 'Input requested'}
      tag={<StatusTag value={item.resolutionState} tone={isActive ? 'warning' : 'default'} />}
      summary={item.summary}
      tone={isActive ? 'warning' : 'default'}
    >
      <MarkdownText value={item.prompt} className={styles.cardText} />
      <form className={styles.requestForm} onSubmit={(event) => void handleSubmit(event)}>
        {resolvedQuestions.map((question) => (
          <RuntimeInputQuestion
            key={question.id}
            question={question}
            value={drafts[question.id] ?? ''}
            onChange={(nextValue) =>
              setDrafts((current) => ({
                ...current,
                [question.id]: nextValue,
              }))
            }
          />
        ))}
        {isActive ? (
          <div className={styles.requestFooter}>
            {requestUi?.error ? <p className={styles.requestError}>{requestUi.error}</p> : null}
            <button type="submit" className={styles.submitRequestButton} disabled={!canSubmit}>
              {requestUi?.isSubmitting ? 'Submitting...' : 'Continue'}
            </button>
          </div>
        ) : null}
      </form>
    </RowCard>
  )
}

function RuntimeInputResponseItem({
  item,
}: {
  item: ConversationUserInputResponseRenderItem
}) {
  return (
    <RowCard
      kicker="Runtime Input Response"
      title={item.title ?? 'Answer submitted'}
      summary={item.summary}
      tag={<StatusTag value={item.requestId} />}
    >
      <MarkdownText value={item.text} className={styles.cardText} />
      {item.answers.length > 0 ? (
        <div className={styles.detailList}>
          {item.answers.map((answer) => (
            <div key={answer.key} className={styles.detailListItem}>
              <strong>{answer.label}</strong>
              <span>{answer.values.length > 0 ? answer.values.join(', ') : '(no answer text)'}</span>
            </div>
          ))}
        </div>
      ) : null}
    </RowCard>
  )
}

function DiffSummaryItem({ item }: { item: ConversationDiffSummaryRenderItem }) {
  const stats = [
    item.stats.added !== null ? `+${item.stats.added}` : null,
    item.stats.removed !== null ? `-${item.stats.removed}` : null,
    item.stats.changed !== null ? `~${item.stats.changed}` : null,
  ].filter((value): value is string => Boolean(value))

  return (
    <RowCard kicker="Diff Summary" title={item.title ?? 'Change summary'} summary={item.summary}>
      {stats.length > 0 ? (
        <div className={styles.statList}>
          {stats.map((value) => (
            <span key={value} className={styles.statChip}>
              {value}
            </span>
          ))}
        </div>
      ) : null}
      {item.files.length > 0 ? (
        <ul className={styles.fileList}>
          {item.files.map((file) => (
            <li key={file}>{file}</li>
          ))}
        </ul>
      ) : null}
    </RowCard>
  )
}

function FileChangeSummaryItem({ item }: { item: ConversationFileChangeSummaryRenderItem }) {
  return (
    <RowCard
      kicker="File Change"
      title={item.filePath ?? 'File change'}
      tag={<StatusTag value={item.changeType} />}
      summary={item.summary}
    />
  )
}

function StatusBlockItem({ item }: { item: ConversationStatusBlockRenderItem }) {
  const tone =
    item.statusLabel === 'error' ? 'danger' : item.statusLabel === 'superseded' ? 'warning' : 'default'
  const tagTone = tone === 'danger' ? 'danger' : tone === 'warning' ? 'warning' : 'default'

  return (
    <RowCard
      kicker="Status"
      title={item.title ?? 'Execution status'}
      tag={<StatusTag value={item.statusLabel} tone={tagTone} />}
      summary={item.summary}
      tone={tone}
    />
  )
}

function UnsupportedItem({ item }: { item: ConversationUnsupportedRenderItem }) {
  return <div className={styles.unsupportedFallback}>Unsupported content: {item.partType}</div>
}

function renderItem(
  item: ConversationRenderItem,
  message: ConversationRenderMessage,
  onQuoteMessage: Props['onQuoteMessage'],
  activeRequest: ActiveConversationRequest | null,
  requestUi: Props['requestUi'],
): ReactNode {
  switch (item.kind) {
    case 'assistant_text':
    case 'user_text':
      return <TextItem item={item} tone={message.roleTone} onQuoteMessage={onQuoteMessage} />
    case 'reasoning':
      return <ReasoningItem item={item} />
    case 'tool_call':
      return <ToolCallItem item={item} />
    case 'tool_result':
      return <ToolResultItem item={item} />
    case 'plan_block':
      return <PlanBlockItem item={item} />
    case 'plan_step_update':
      return <PlanStepUpdateItem item={item} />
    case 'approval_request':
      return <ApprovalRequestItem item={item} activeRequest={activeRequest} requestUi={requestUi} />
    case 'user_input_request':
      return <RuntimeInputRequestItem item={item} activeRequest={activeRequest} requestUi={requestUi} />
    case 'user_input_response':
      return <RuntimeInputResponseItem item={item} />
    case 'diff_summary':
      return <DiffSummaryItem item={item} />
    case 'file_change_summary':
      return <FileChangeSummaryItem item={item} />
    case 'status_block':
      return <StatusBlockItem item={item} />
    case 'unsupported':
      return <UnsupportedItem item={item} />
    default:
      return null
  }
}

function MessageStatusRow({
  message,
}: {
  message: ConversationRenderMessage
}) {
  if (!message.isStreaming && !message.hasError) {
    return null
  }

  return (
    <div className={styles.messageStatusRow}>
      {message.isStreaming ? <span className={styles.streamingBadge}>streaming</span> : null}
      {message.hasError ? <span className={styles.errorBadge}>error</span> : null}
    </div>
  )
}

function MessageActionRow({
  actions,
}: {
  actions: ConversationSurfaceMessageAction[]
}) {
  if (actions.length === 0) {
    return null
  }

  return (
    <div className={styles.messageActions}>
      {actions.map((action) => (
        <button
          key={action.key}
          type="button"
          className={styles.messageActionButton}
          disabled={action.disabled}
          onClick={() => action.onPress()}
        >
          {action.label}
        </button>
      ))}
    </div>
  )
}

function renderMessage({
  message,
  actions,
  onQuoteMessage,
  activeRequest,
  requestUi,
}: {
  message: ConversationRenderMessage
  actions: ConversationSurfaceMessageAction[]
  onQuoteMessage: Props['onQuoteMessage']
  activeRequest: ActiveConversationRequest | null
  requestUi: Props['requestUi']
}) {
  return (
    <article key={message.messageId} className={`${styles.messageRow} ${styles[message.roleTone]}`}>
      <div className={styles.messageStack}>
        {message.items.map((item) => (
          <div key={item.key} className={styles.messageItem}>
            {renderItem(item, message, onQuoteMessage, activeRequest, requestUi)}
          </div>
        ))}
        {message.showTyping ? (
          <div className={styles.messageItem}>
            <div className={`${styles.textCard} ${styles.assistantTextCard}`}>
              <TypingIndicator />
            </div>
          </div>
        ) : null}
        <MessageStatusRow message={message} />
        <MessageActionRow actions={actions} />
        {message.errorText ? <p className={styles.messageError}>{message.errorText}</p> : null}
      </div>
    </article>
  )
}

function WorkingRow({
  label,
  elapsedLabel,
}: {
  label: string | null | undefined
  elapsedLabel: string | null
}) {
  return (
    <div className={styles.workingRow}>
      <Spinner />
      <span className={styles.workingLabel}>{label ?? 'Working'}</span>
      {elapsedLabel ? <span className={styles.workingTimer}>{elapsedLabel}</span> : null}
    </div>
  )
}

function DoneSeparator({
  durationLabel,
}: {
  durationLabel: string | null
}) {
  return (
    <div className={styles.doneSeparator}>
      <span>Done</span>
      {durationLabel ? <span>{durationLabel}</span> : null}
    </div>
  )
}

function Composer({
  value,
  disabled,
  placeholder,
  hint,
  canStop,
  isStreaming,
  onChange,
  onSubmit,
  onStop,
  onKeyDown,
}: {
  value: string
  disabled: boolean
  placeholder: string
  hint: ReactNode
  canStop: boolean
  isStreaming: boolean
  onChange?: (draft: string) => void
  onSubmit?: () => void
  onStop?: () => void
  onKeyDown?: Props['onComposerKeyDown']
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 56), 220)}px`
  }, [value])

  const buttonLabel = isStreaming && canStop ? 'Stop' : 'Send'
  const buttonDisabled = isStreaming ? !canStop : disabled || value.trim().length === 0

  return (
    <div className={styles.composerWrap}>
      <div className={`${styles.composerFrame} ${disabled ? styles.composerFrameDisabled : ''}`}>
        <textarea
          ref={textareaRef}
          className={styles.composer}
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(event) => onChange?.(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          className={`${styles.composerButton} ${isStreaming && canStop ? styles.stopButton : ''}`}
          disabled={buttonDisabled}
          onClick={() => {
            if (isStreaming && canStop) {
              onStop?.()
              return
            }
            onSubmit?.()
          }}
        >
          {buttonLabel}
        </button>
      </div>
      <p className={styles.composerHint}>{hint}</p>
    </div>
  )
}

export function ExecutionConversationSurface({
  model,
  connectionState,
  isLoading,
  errorMessage,
  contextLabel,
  emptyTitle,
  emptyHint,
  showHeader = true,
  showComposer = false,
  composerValue = '',
  composerDisabled = false,
  composerPlaceholder = 'Write a message...',
  composerHint = null,
  onComposerValueChange,
  onComposerSubmit,
  onComposerKeyDown,
  messageActions = {},
  onQuoteMessage,
  canStop = false,
  onStop,
  transcriptStatus = null,
  activeRequest = null,
  requestUi = null,
}: Props) {
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)
  const [autoFollow, setAutoFollow] = useState(true)
  const [elapsedMs, setElapsedMs] = useState<number | null>(transcriptStatus?.lastDurationMs ?? null)

  useEffect(() => {
    const startedAt = transcriptStatus?.startedAt ?? null
    if (transcriptStatus?.isStreaming && startedAt) {
      setElapsedMs(Date.now() - startedAt)
      const timer = window.setInterval(() => {
        setElapsedMs(Date.now() - startedAt)
      }, 1000)
      return () => window.clearInterval(timer)
    }

    setElapsedMs(transcriptStatus?.lastDurationMs ?? null)
    return undefined
  }, [transcriptStatus?.isStreaming, transcriptStatus?.lastDurationMs, transcriptStatus?.startedAt])

  useEffect(() => {
    if (!autoFollow) {
      return
    }
    transcriptEndRef.current?.scrollIntoView({
      block: 'end',
    })
  }, [activeRequest?.requestId, autoFollow, model, transcriptStatus?.isStreaming])

  const entries: ConversationRenderEntry[] = model?.entries ?? []
  const hasMessages = entries.length > 0
  const showWorkingRow = Boolean(transcriptStatus?.isStreaming)
  const showDoneSeparator = Boolean(
    !transcriptStatus?.isStreaming &&
      transcriptStatus?.lastDurationMs !== null &&
      transcriptStatus?.lastDurationMs !== undefined,
  )
  const elapsedLabel = formatDuration(elapsedMs)
  const doneDurationLabel = formatDuration(transcriptStatus?.lastDurationMs ?? null)

  return (
    <section className={styles.surface}>
      {showHeader ? (
        <header className={styles.header}>
          <div className={styles.connectionWrap}>
            <span className={`${styles.connectionDot} ${styles[connectionState]}`} aria-hidden="true" />
            <span className={styles.connectionLabel}>{formatConnectionLabel(connectionState)}</span>
          </div>
          {contextLabel ? <div className={styles.contextLabel}>{contextLabel}</div> : null}
        </header>
      ) : null}

      {errorMessage ? (
        <div className={styles.errorBanner} role="alert">
          {errorMessage}
        </div>
      ) : null}

      <div
        className={styles.thread}
        onScroll={(event) => {
          setAutoFollow(isNearBottom(event.currentTarget))
        }}
      >
        {!hasMessages && isLoading ? (
          <div className={styles.loadingState}>
            <LoadingDots />
            <p>Loading conversation...</p>
          </div>
        ) : hasMessages ? (
          <div className={styles.transcript}>
            {entries.map((entry) => {
              if (entry.kind === 'message') {
                return renderMessage({
                  message: entry.message,
                  actions: messageActions[entry.message.messageId] ?? [],
                  onQuoteMessage,
                  activeRequest,
                  requestUi,
                })
              }

              return (
                <details key={entry.key} className={styles.replayGroup}>
                  <summary className={styles.replaySummary}>{entry.label}</summary>
                  <div className={styles.replayMessages}>
                    {entry.messages.map((message) =>
                      renderMessage({
                        message,
                        actions: messageActions[message.messageId] ?? [],
                        onQuoteMessage,
                        activeRequest,
                        requestUi,
                      }),
                    )}
                  </div>
                </details>
              )
            })}
            {showWorkingRow ? (
              <WorkingRow label={transcriptStatus?.workingLabel} elapsedLabel={elapsedLabel} />
            ) : null}
            {showDoneSeparator ? <DoneSeparator durationLabel={doneDurationLabel} /> : null}
            <div ref={transcriptEndRef} />
          </div>
        ) : (
          <div className={styles.emptyState}>
            <h3 className={styles.emptyTitle}>{emptyTitle}</h3>
            <p className={styles.emptyHint}>{emptyHint}</p>
          </div>
        )}
      </div>

      {showComposer ? (
        <Composer
          value={composerValue}
          disabled={composerDisabled}
          placeholder={composerPlaceholder}
          hint={composerHint}
          canStop={canStop}
          isStreaming={Boolean(transcriptStatus?.isStreaming)}
          onChange={onComposerValueChange}
          onSubmit={onComposerSubmit}
          onStop={onStop}
          onKeyDown={onComposerKeyDown}
        />
      ) : null}
    </section>
  )
}
