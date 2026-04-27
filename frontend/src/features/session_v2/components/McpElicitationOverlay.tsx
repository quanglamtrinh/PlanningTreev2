import { useMemo, useState } from 'react'
import type { PendingServerRequest } from '../contracts'

type McpElicitationOverlayProps = {
  request: PendingServerRequest
  onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  onReject: (requestId: string, reason?: string | null) => Promise<void>
}

type FormField = {
  id: string
  label: string
  required: boolean
  type: string
  description: string | null
  enumValues: string[]
}

function parseFields(payload: Record<string, unknown>): FormField[] {
  const schema = payload.requestedSchema ?? payload.schema
  if (!schema || typeof schema !== 'object') return []
  const schemaRecord = schema as Record<string, unknown>
  const properties = schemaRecord.properties
  const requiredRaw = Array.isArray(schemaRecord.required) ? schemaRecord.required : []
  const required = new Set(requiredRaw.filter((value): value is string => typeof value === 'string'))
  if (!properties || typeof properties !== 'object') return []

  return Object.entries(properties as Record<string, unknown>).map(([id, row]) => {
    const record = row && typeof row === 'object' ? (row as Record<string, unknown>) : {}
    const enumRaw = Array.isArray(record.enum) ? record.enum : []
    return {
      id,
      label: typeof record.title === 'string' ? record.title : id,
      required: required.has(id),
      type: typeof record.type === 'string' ? record.type : 'string',
      description: typeof record.description === 'string' ? record.description : null,
      enumValues: enumRaw.map(String),
    }
  })
}

function coerceValue(field: FormField, raw: string): unknown {
  const trimmed = raw.trim()
  if (field.type === 'boolean') return trimmed === 'true'
  if (field.type === 'number' || field.type === 'integer') {
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : trimmed
  }
  return trimmed
}

function resultForAction(action: 'accept' | 'decline' | 'cancel', response: Record<string, unknown>): Record<string, unknown> {
  if (action === 'accept') {
    return { action: 'accept', response }
  }
  return { action }
}

export function McpElicitationOverlay({ request, onResolve, onReject }: McpElicitationOverlayProps) {
  const fields = useMemo(() => parseFields(request.payload), [request.payload])
  const [values, setValues] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const message = typeof request.payload.message === 'string' ? request.payload.message : null
  const title = typeof request.payload.title === 'string' ? request.payload.title : 'MCP elicitation'

  async function submit(action: 'accept' | 'decline' | 'cancel') {
    if (action !== 'accept') {
      await onResolve(request.requestId, resultForAction(action, {}))
      return
    }
    setIsSubmitting(true)
    try {
      const formData: Record<string, unknown> = {}
      for (const field of fields) {
        const value = values[field.id] ?? ''
        if (field.required && value.trim().length === 0) {
          setIsSubmitting(false)
          return
        }
        if (value.trim().length > 0) {
          formData[field.id] = coerceValue(field, value)
        }
      }
      await onResolve(request.requestId, resultForAction('accept', formData))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="sessionV2Overlay">
      <div className="sessionV2OverlayCard">
        <header className="sessionV2OverlayHeader">
          <h3>{title}</h3>
          <p>{message ?? request.method}</p>
        </header>
        <div className="sessionV2OverlayBody">
          {fields.length === 0 ? (
            <pre className="sessionV2Json">{JSON.stringify(request.payload, null, 2)}</pre>
          ) : (
            <div className="sessionV2FieldList">
              {fields.map((field) => (
                <label key={field.id} className="sessionV2Field">
                  {field.label}{field.required ? ' *' : ''}
                  {field.description ? <span>{field.description}</span> : null}
                  {field.enumValues.length > 0 ? (
                    <select
                      value={values[field.id] ?? ''}
                      onChange={(event) => setValues((previous) => ({ ...previous, [field.id]: event.target.value }))}
                    >
                      <option value="">Select...</option>
                      {field.enumValues.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  ) : field.type === 'boolean' ? (
                    <select
                      value={values[field.id] ?? ''}
                      onChange={(event) => setValues((previous) => ({ ...previous, [field.id]: event.target.value }))}
                    >
                      <option value="">Select...</option>
                      <option value="true">True</option>
                      <option value="false">False</option>
                    </select>
                  ) : (
                    <input
                      type={field.type === 'number' || field.type === 'integer' ? 'number' : 'text'}
                      value={values[field.id] ?? ''}
                      onChange={(event) => setValues((previous) => ({ ...previous, [field.id]: event.target.value }))}
                    />
                  )}
                </label>
              ))}
            </div>
          )}
        </div>
        <footer className="sessionV2OverlayFooter">
          <div className="sessionV2OverlayActions">
            <button type="button" disabled={isSubmitting} onClick={() => void onReject(request.requestId, 'cancel')}>
              Cancel
            </button>
            <button type="button" disabled={isSubmitting} onClick={() => void submit('decline')}>
              Decline
            </button>
            <button type="button" disabled={isSubmitting} onClick={() => void submit('accept')}>
              Submit
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
