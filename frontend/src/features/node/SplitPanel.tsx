import { useEffect, useMemo, useState } from 'react'
import type { DetailState, NodeRecord, SplitMode } from '../../api/types'
import { GRAPH_SPLIT_OPTIONS } from '../graph/splitModes'
import { useProjectStore } from '../../stores/project-store'
import styles from './NodeDetailCard.module.css'

type Props = {
  projectId: string
  node: NodeRecord
  detailState: DetailState | undefined
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

export function SplitPanel({ projectId, node, detailState }: Props) {
  const activeProjectId = useProjectStore((state) => state.activeProjectId)
  const splitNode = useProjectStore((state) => state.splitNode)
  const splitStatus = useProjectStore((state) => state.splitStatus)
  const splitNodeId = useProjectStore((state) => state.splitNodeId)
  const splitMode = useProjectStore((state) => state.splitMode)
  const [selectedMode, setSelectedMode] = useState<SplitMode>('workflow')
  const [submitError, setSubmitError] = useState<string | null>(null)

  const isCurrentNodeSplitting = splitStatus === 'active' && splitNodeId === node.node_id
  const isAnySplitActive = splitStatus === 'active'
  const canConfirmSplit =
    detailState?.frame_confirmed === true &&
    detailState?.clarify_confirmed === true &&
    detailState?.frame_needs_reconfirm !== true
  const selectedOption = useMemo(
    () => GRAPH_SPLIT_OPTIONS.find((option) => option.id === selectedMode) ?? GRAPH_SPLIT_OPTIONS[0],
    [selectedMode],
  )

  useEffect(() => {
    if (isCurrentNodeSplitting && splitMode) {
      setSelectedMode(splitMode)
    }
  }, [isCurrentNodeSplitting, splitMode])

  async function handleConfirmSplit() {
    setSubmitError(null)

    if (activeProjectId !== projectId) {
      setSubmitError('Split is unavailable until this project is active in the current workspace.')
      return
    }

    try {
      await splitNode(node.node_id, selectedMode)
    } catch (error) {
      setSubmitError(toErrorMessage(error))
    }
  }

  return (
    <div className={styles.splitPanel}>
      <div className={styles.splitPanelIntro}>
        <p className={styles.eyebrow}>Split</p>
        <h3 className={styles.title}>Choose how this task should be broken down</h3>
        <p className={styles.body}>
          Pick the split strategy that best matches the shape of the work, then confirm to start the split.
        </p>
      </div>

      {submitError ? (
        <div className={styles.documentErrorPanel} data-testid="split-error-panel">
          <p className={styles.body}>{submitError}</p>
        </div>
      ) : null}

      {!canConfirmSplit || (isAnySplitActive && !isCurrentNodeSplitting) ? (
        <div className={styles.splitHintPanel} data-testid="split-readiness-hint">
          <p className={styles.body}>
            {!canConfirmSplit
              ? 'Confirm the latest frame first. Once the updated frame is confirmed and clarify is clear, you can choose a split mode here.'
              : 'A split is already running for this project. Wait for it to finish before starting another one.'}
          </p>
        </div>
      ) : null}

      <div className={styles.splitOptionsGroup} role="radiogroup" aria-label="Split modes">
        {GRAPH_SPLIT_OPTIONS.map((option) => {
          const selected = option.id === selectedMode
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={selected}
              className={[
                styles.splitOptionCard,
                selected ? styles.splitOptionCardSelected : '',
              ]
                .filter(Boolean)
                .join(' ')}
              data-testid={`split-option-${option.id}`}
              disabled={!canConfirmSplit || isAnySplitActive}
              onClick={() => {
                setSelectedMode(option.id)
                setSubmitError(null)
              }}
            >
              <span className={styles.splitOptionHeader}>
                <span className={styles.splitOptionTitle}>{option.label}</span>
                {selected ? <span className={styles.splitOptionBadge}>Selected</span> : null}
              </span>
              <span className={styles.splitOptionDescription}>{option.description}</span>
            </button>
          )
        })}
      </div>

      <div className={styles.splitSelectionSummary}>
        <p className={styles.body}>
          Current mode: <strong>{selectedOption.label}</strong>
        </p>
      </div>

      <div className={styles.tabConfirmRow}>
        <button
          type="button"
          className={styles.confirmButton}
          data-testid="confirm-split-button"
          disabled={!canConfirmSplit || isAnySplitActive}
          onClick={() => void handleConfirmSplit()}
        >
          {isCurrentNodeSplitting ? 'Splitting...' : 'Confirm'}
        </button>
      </div>
    </div>
  )
}
