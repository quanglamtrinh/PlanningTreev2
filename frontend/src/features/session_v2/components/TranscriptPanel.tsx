import type { SessionItem, SessionTurn } from '../contracts'

type TranscriptPanelProps = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
}

function renderItemText(item: SessionItem): string {
  const payload = item.payload
  if (typeof payload.text === 'string') {
    return payload.text
  }
  if (Array.isArray(payload.content)) {
    return payload.content
      .map((entry) => {
        if (!entry || typeof entry !== 'object') {
          return ''
        }
        const row = entry as Record<string, unknown>
        if (typeof row.text === 'string') {
          return row.text
        }
        if (typeof row.output === 'string') {
          return row.output
        }
        return ''
      })
      .join('\n')
      .trim()
  }
  if (typeof payload.output === 'string') {
    return payload.output
  }
  return JSON.stringify(payload)
}

export function TranscriptPanel({ threadId, turns, itemsByTurn }: TranscriptPanelProps) {
  if (!threadId) {
    return (
      <section className="sessionV2Transcript">
        <div className="sessionV2Empty">No active thread</div>
      </section>
    )
  }

  return (
    <section className="sessionV2Transcript">
      {turns.length === 0 ? (
        <div className="sessionV2Empty">No turns yet.</div>
      ) : (
        turns.map((turn) => {
          const key = `${threadId}:${turn.id}`
          const items = itemsByTurn[key] ?? []
          return (
            <article key={turn.id} className="sessionV2Turn">
              <header className="sessionV2TurnHeader">
                <strong>{turn.id}</strong>
                <span>{turn.status}</span>
              </header>
              <div className="sessionV2TurnItems">
                {items.length === 0 ? (
                  <div className="sessionV2EmptyInline">No items</div>
                ) : (
                  items.map((item) => (
                    <div key={item.id} className={`sessionV2Item sessionV2Item-${item.kind}`}>
                      <div className="sessionV2ItemMeta">
                        <span>{item.kind}</span>
                        <small>{item.status}</small>
                      </div>
                      <pre className="sessionV2ItemText">{renderItemText(item)}</pre>
                    </div>
                  ))
                )}
              </div>
            </article>
          )
        })
      )}
    </section>
  )
}

