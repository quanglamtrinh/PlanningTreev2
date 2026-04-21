import type { SessionThread } from '../contracts'

type ThreadListPanelProps = {
  threads: SessionThread[]
  activeThreadId: string | null
  onCreateThread: () => void
  onRefresh: () => void
  onSelectThread: (threadId: string) => void
  onResumeThread: (threadId: string) => void
  onForkThread: (threadId: string) => void
}

export function ThreadListPanel({
  threads,
  activeThreadId,
  onCreateThread,
  onRefresh,
  onSelectThread,
  onResumeThread,
  onForkThread,
}: ThreadListPanelProps) {
  return (
    <aside className="sessionV2ThreadList">
      <header className="sessionV2ThreadListHeader">
        <h2>Threads</h2>
        <div className="sessionV2ThreadListActions">
          <button type="button" onClick={onCreateThread}>New</button>
          <button type="button" onClick={onRefresh}>Refresh</button>
        </div>
      </header>
      <ul className="sessionV2ThreadListItems">
        {threads.map((thread) => {
          const isActive = activeThreadId === thread.id
          return (
            <li key={thread.id} className={isActive ? 'sessionV2ThreadRow active' : 'sessionV2ThreadRow'}>
              <button
                type="button"
                className="sessionV2ThreadMain"
                onClick={() => onSelectThread(thread.id)}
                title={thread.id}
              >
                <span className="sessionV2ThreadName">{thread.name ?? thread.id}</span>
                <small>{thread.status.type}</small>
              </button>
              <div className="sessionV2ThreadRowActions">
                <button type="button" onClick={() => onResumeThread(thread.id)}>Resume</button>
                <button type="button" onClick={() => onForkThread(thread.id)}>Fork</button>
              </div>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}

