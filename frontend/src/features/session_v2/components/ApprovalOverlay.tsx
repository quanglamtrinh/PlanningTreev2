import { useMemo, useState } from 'react'
import type { PendingServerRequest } from '../contracts'

type ApprovalOverlayProps = {
  request: PendingServerRequest
  onResolve: (result: Record<string, unknown>) => Promise<void>
  onReject: (reason?: string | null) => Promise<void>
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

export function ApprovalOverlay({ request, onResolve, onReject }: ApprovalOverlayProps) {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [customReason, setCustomReason] = useState('')
  const choices = useMemo(() => approvalChoices(request.method), [request.method])

  async function handleChoice(choice: ApprovalChoice) {
    setIsSubmitting(true)
    try {
      if (choice.result) {
        await onResolve({
          ...choice.result,
          reason: customReason.trim().length > 0 ? customReason.trim() : null,
        })
      } else {
        await onReject(choice.rejectReason ?? 'cancel')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="sessionV2Overlay">
      <div className="sessionV2OverlayCard">
        <header className="sessionV2OverlayHeader">
          <h3>Approval required</h3>
          <p>{request.method}</p>
        </header>
        <div className="sessionV2OverlayBody">
          <pre className="sessionV2Json">{JSON.stringify(request.payload, null, 2)}</pre>
          <label className="sessionV2Field">
            Reason (optional)
            <input
              type="text"
              value={customReason}
              onChange={(event) => setCustomReason(event.target.value)}
              placeholder="Add an operator note"
            />
          </label>
          <div className="sessionV2Options">
            {choices.map((choice) => (
              <button key={choice.id} type="button" disabled={isSubmitting} className="sessionV2Option" onClick={() => void handleChoice(choice)}>
                {choice.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

