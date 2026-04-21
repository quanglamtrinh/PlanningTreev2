import { useMemo, useState } from 'react'
import type { PendingServerRequest } from '../contracts'

type McpElicitationOverlayProps = {
  request: PendingServerRequest
  onResolve: (result: Record<string, unknown>) => Promise<void>
  onReject: (reason?: string | null) => Promise<void>
}

type FormField = {
  id: string
  label: string
  required: boolean
}

function parseFields(payload: Record<string, unknown>): FormField[] {
  const schema = payload.requestedSchema
  if (!schema || typeof schema !== 'object') {
    return []
  }
  const schemaRecord = schema as Record<string, unknown>
  const properties = schemaRecord.properties
  const requiredRaw = Array.isArray(schemaRecord.required) ? schemaRecord.required : []
  const required = new Set(requiredRaw.filter((value): value is string => typeof value === 'string'))
  if (!properties || typeof properties !== 'object') {
    return []
  }
  const fields: FormField[] = []
  for (const [id, row] of Object.entries(properties as Record<string, unknown>)) {
    const label = row && typeof row === 'object' && typeof (row as Record<string, unknown>).title === 'string'
      ? String((row as Record<string, unknown>).title)
      : id
    fields.push({ id, label, required: required.has(id) })
  }
  return fields
}

export function McpElicitationOverlay({ request, onResolve, onReject }: McpElicitationOverlayProps) {
  const fields = useMemo(() => parseFields(request.payload), [request.payload])
  const [values, setValues] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submit() {
    setIsSubmitting(true)
    try {
      const formData: Record<string, unknown> = {}
      for (const field of fields) {
        const value = (values[field.id] ?? '').trim()
        if (field.required && value.length === 0) {
          setIsSubmitting(false)
          return
        }
        if (value.length > 0) {
          formData[field.id] = value
        }
      }
      await onResolve({ response: formData })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="sessionV2Overlay">
      <div className="sessionV2OverlayCard">
        <header className="sessionV2OverlayHeader">
          <h3>MCP elicitation</h3>
          <p>{request.method}</p>
        </header>
        <div className="sessionV2OverlayBody">
          {fields.length === 0 ? (
            <pre className="sessionV2Json">{JSON.stringify(request.payload, null, 2)}</pre>
          ) : (
            <div className="sessionV2FieldList">
              {fields.map((field) => (
                <label key={field.id} className="sessionV2Field">
                  {field.label}{field.required ? ' *' : ''}
                  <input
                    type="text"
                    value={values[field.id] ?? ''}
                    onChange={(event) => {
                      const next = event.target.value
                      setValues((previous) => ({ ...previous, [field.id]: next }))
                    }}
                  />
                </label>
              ))}
            </div>
          )}
        </div>
        <footer className="sessionV2OverlayFooter">
          <div className="sessionV2OverlayActions">
            <button type="button" disabled={isSubmitting} onClick={() => void onReject('cancel')}>
              Cancel
            </button>
            <button type="button" disabled={isSubmitting} onClick={() => void submit()}>
              Submit
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}

