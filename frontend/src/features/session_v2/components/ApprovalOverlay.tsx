import { useMemo, useState } from 'react'
import type { PendingServerRequest } from '../contracts'

type ApprovalOverlayProps = {
  request: PendingServerRequest
  onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  onReject: (requestId: string, reason?: string | null) => Promise<void>
  variant?: 'overlay' | 'inline'
}

type ApprovalChoice = {
  id: string
  label: string
  result: Record<string, unknown> | null
  rejectReason: string | null
}

function approvalChoices(method: PendingServerRequest['method']): ApprovalChoice[] {
  if (method === 'item/permissions/requestApproval') {
    return [
      { id: 'accept', label: 'Accept', result: { decision: 'accept', scope: 'turn' }, rejectReason: null },
      { id: 'accept-session', label: 'Accept for session', result: { decision: 'acceptForSession' }, rejectReason: null },
      { id: 'decline', label: 'Decline', result: { decision: 'decline' }, rejectReason: null },
      { id: 'cancel', label: 'Cancel', result: null, rejectReason: 'cancel' },
    ]
  }
  return [
    { id: 'accept', label: 'Accept', result: { decision: 'accept' }, rejectReason: null },
    { id: 'accept-session', label: 'Accept for session', result: { decision: 'acceptForSession' }, rejectReason: null },
    { id: 'decline', label: 'Decline', result: { decision: 'decline' }, rejectReason: null },
    { id: 'cancel', label: 'Cancel', result: null, rejectReason: 'cancel' },
  ]
}

function requestSummary(request: PendingServerRequest): string {
  const command = request.payload.command
  if (typeof command === 'string' && command.trim()) {
    return command
  }
  if (Array.isArray(command)) {
    return command.map((part) => String(part)).join(' ')
  }
  return request.method
}

function choiceClassName(choice: ApprovalChoice): string {
  if (choice.id === 'accept' || choice.id === 'accept-session') {
    return 'sessionV2ApprovalOption sessionV2ApprovalOptionPrimary'
  }
  if (choice.id === 'decline') {
    return 'sessionV2ApprovalOption sessionV2ApprovalOptionDanger'
  }
  return 'sessionV2ApprovalOption'
}

export function ApprovalOverlay({ request, onResolve, onReject, variant = 'overlay' }: ApprovalOverlayProps) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [customReason, setCustomReason] = useState('')
  const choices = useMemo(() => approvalChoices(request.method), [request.method])

  async function handleChoice(choice: ApprovalChoice) {
    setIsSubmitting(true)
    try {
      if (choice.result) {
        await onResolve(request.requestId, {
          ...choice.result,
          reason: customReason.trim().length > 0 ? customReason.trim() : null,
        })
      } else {
        await onReject(request.requestId, choice.rejectReason ?? 'cancel')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const content = (
    <div className={variant === 'inline' ? 'sessionV2ApprovalCard' : 'sessionV2OverlayCard'}>
      <header className={variant === 'inline' ? 'sessionV2ApprovalHeader' : 'sessionV2OverlayHeader'}>
        <div>
          <h3>Approval required</h3>
          <p>{request.method}</p>
        </div>
      </header>
      <div className={variant === 'inline' ? 'sessionV2ApprovalBody' : 'sessionV2OverlayBody'}>
        <div className="sessionV2ApprovalSummary">{requestSummary(request)}</div>
        <details className="sessionV2ApprovalDetails">
          <summary>Command / request payload</summary>
          <pre className="sessionV2Json">{JSON.stringify(request.payload, null, 2)}</pre>
        </details>
        <label className="sessionV2Field">
          Reason (optional)
          <input
            type="text"
            value={customReason}
            onChange={(event) => setCustomReason(event.target.value)}
            placeholder="Add an operator note"
          />
        </label>
        <div className="sessionV2ApprovalOptions">
          {choices.map((choice) => (
            <button key={choice.id} type="button" disabled={isSubmitting} className={choiceClassName(choice)} onClick={() => void handleChoice(choice)}>
              {choice.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )

  if (variant === 'inline') {
    return <div className="sessionV2ApprovalInline">{content}</div>
  }

  return <div className="sessionV2Overlay">{content}</div>
}
