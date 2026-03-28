import type { ToolItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'

function toolLabel(toolType: ToolItem['toolType']) {
  if (toolType === 'commandExecution') return 'Command'
  if (toolType === 'fileChange') return 'File Change'
  return 'Tool'
}

export function ToolRow({ item }: { item: ToolItem }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-tool">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>{toolLabel(item.toolType)}</div>
            <h3 className={styles.cardTitle}>{item.title || item.toolName || 'Tool activity'}</h3>
          </div>
          <div className={styles.cardMeta}>
            <span className={styles.statusPill}>{item.status}</span>
            {item.toolName ? <span>{item.toolName}</span> : null}
            {item.exitCode != null ? <span>exit {item.exitCode}</span> : null}
          </div>
        </div>

        {item.argumentsText ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Arguments</div>
            <pre className={styles.plainPre}>{item.argumentsText}</pre>
          </div>
        ) : null}

        {item.outputText ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Output</div>
            <pre className={styles.plainPre}>{item.outputText}</pre>
          </div>
        ) : null}

        {item.outputFiles.length ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Files</div>
            <div className={styles.fileList}>
              {item.outputFiles.map((file) => (
                <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                  <div className={styles.fileMeta}>
                    <span className={styles.statusPill}>{file.changeType}</span>
                    <code>{file.path}</code>
                  </div>
                  {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  )
}
