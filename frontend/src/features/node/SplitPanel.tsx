import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { DetailState, NodeRecord, SplitMode } from '../../api/types'
import { GRAPH_SPLIT_OPTIONS } from '../graph/splitModes'
import { AgentSpinner, SPINNER_WORDS_SPLITTING } from '../../components/AgentSpinner'
import { useDetailStateStore } from '../../stores/detail-state-store'
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


type SplitModeInfo = {
  modeDescription: string
  subtasks: { title: string; body: string }[]
  briefExplain: string
  whenItWorksBest: string
}

const SPLIT_MODE_ORIGINAL_TASK =
  'Allow users to change their profile picture from the profile page. Users should be able to choose an image from their device, preview it, save it, and then see the new avatar across the app.'

const SPLIT_MODE_INFO: Record<SplitMode, SplitModeInfo> = {
  workflow: {
    modeDescription: 'Break the task according to the user journey from start to finish.',
    subtasks: [
      {
        title: 'Let users start changing their avatar from the profile page',
        body: 'Users go to their profile page, click "Change avatar," and choose an image from their computer or phone. After selecting an image, the system shows the selected image so users know what they are about to upload.',
      },
      {
        title: 'Let users review and confirm the image before saving',
        body: 'Users can preview the image, crop it if needed, cancel if they picked the wrong file, or click "Save" to confirm that this should become their new avatar.',
      },
      {
        title: 'Save the new image and update the avatar across the app',
        body: 'After users click save, the system uploads the image, updates the user profile, and shows the new avatar on the profile page, navigation bar, comments, posts, and anywhere else the avatar appears.',
      },
    ],
    briefExplain:
      'The user starts changing the avatar, reviews or edits the image, then saves it and sees the result.',
    whenItWorksBest: 'This mode works well when you want to split the task by user experience.',
  },
  simplify_workflow: {
    modeDescription:
      'Break the task by building the smallest useful version first, then adding more complete behavior step by step.',
    subtasks: [
      {
        title: 'Build the simplest version: users can choose an image and save it as their avatar',
        body: 'No crop, no progress bar, and no complex error handling yet. Just add a file picker, upload the selected image, and show the new avatar on the profile page. The goal is to prove that the basic flow works.',
      },
      {
        title: 'Add the important pieces needed for real-world use',
        body: 'Add file type validation, file size limits, upload failure messages, disabled save state while uploading, and protection against unsupported files.',
      },
      {
        title: 'Improve the experience with preview, cropping, loading states, and polish',
        body: 'Add a better preview, square crop support, loading/progress states, cancel behavior, success messages, and handling for slow networks or users changing their mind midway.',
      },
    ],
    briefExplain:
      'First build choose image, upload, and avatar changes successfully. Then add validation, errors, crop, loading, and better UX.',
    whenItWorksBest: 'This mode works well when you want to avoid building too much too early.',
  },
  phase_breakdown: {
    modeDescription:
      'Break the task into delivery phases, from a visible version to a production-ready version.',
    subtasks: [
      {
        title: 'Phase 1: Build the UI and basic flow so the feature shape is visible',
        body: 'Add the "Change avatar" button, image picker modal, preview area, and save/cancel buttons. At this stage, the upload can be mocked or not fully connected yet. The goal is for the team to see how the feature will behave.',
      },
      {
        title: 'Phase 2: Connect the feature to backend and storage so it works end to end',
        body: 'Upload the image to the server or cloud storage, save the new avatar URL to the user profile, reload the user data after saving, and make sure the new avatar still appears correctly after refreshing the page.',
      },
      {
        title: 'Phase 3: Harden the feature before release',
        body: 'Add validation, error handling, loading states, retry behavior, file upload security, file size limits, old-image cleanup if needed, key tests, and final UI polish.',
      },
    ],
    briefExplain:
      'Phase 1 makes the shape visible. Phase 2 makes it work for real end to end. Phase 3 makes it solid enough to release.',
    whenItWorksBest: 'This mode works well when the task needs several levels of completion.',
  },
  agent_breakdown: {
    modeDescription:
      'Break the task by technical execution boundaries and system responsibilities, not only by the user journey.',
    subtasks: [
      {
        title: 'Prepare the avatar storage foundation',
        body: 'Design how the avatar is stored in the user model, decide where uploaded images live, create the upload endpoint, handle file naming, access permissions, file size limits, and accepted image formats.',
      },
      {
        title: 'Connect the frontend profile page to the upload system',
        body: 'Add the image selection UI in the profile page, call the upload API, update the user avatar URL, refresh user data in app state/cache, and make sure the new avatar appears in all components that use user data.',
      },
      {
        title: 'Finalize migration, cleanup, and system-level error handling',
        body: 'Handle old avatar images, prevent unused files from piling up, add logging for upload failures, secure the upload endpoint, write frontend/backend tests, and remove temporary or duplicated logic if the avatar was previously hardcoded.',
      },
    ],
    briefExplain:
      'First build the backend/storage foundation, then connect the frontend to that system, then clean up, secure, test, and stabilize.',
    whenItWorksBest:
      'This mode works well when the task has multiple technical parts and dependencies.',
  },
}

export function SplitPanel({ projectId, node, detailState }: Props) {
  const navigate = useNavigate()
  const wasCurrentNodeSplittingRef = useRef(false)
  const activeProjectId = useProjectStore((state) => state.activeProjectId)
  const splitNode = useProjectStore((state) => state.splitNode)
  const splitStatus = useProjectStore((state) => state.splitStatus)
  const splitNodeId = useProjectStore((state) => state.splitNodeId)
  const splitMode = useProjectStore((state) => state.splitMode)
  const loadDetailState = useDetailStateStore((state) => state.loadDetailState)
  const [selectedMode, setSelectedMode] = useState<SplitMode>('workflow')
  const [infoMode, setInfoMode] = useState<SplitMode | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const isCurrentNodeSplitting = splitStatus === 'active' && splitNodeId === node.node_id
  const isAnySplitActive = splitStatus === 'active'
  const splitConfirmed =
    detailState?.split_confirmed === true ||
    node.workflow?.split_confirmed === true ||
    Boolean(node.review_node_id)
  const canConfirmSplit =
    !splitConfirmed &&
    detailState?.frame_confirmed === true &&
    detailState?.clarify_confirmed === true &&
    detailState?.frame_needs_reconfirm !== true
  const selectedOption = useMemo(
    () => GRAPH_SPLIT_OPTIONS.find((option) => option.id === selectedMode) ?? GRAPH_SPLIT_OPTIONS[0],
    [selectedMode],
  )
  const infoOption = useMemo(
    () => GRAPH_SPLIT_OPTIONS.find((option) => option.id === infoMode) ?? null,
    [infoMode],
  )
  const infoContent = infoMode ? SPLIT_MODE_INFO[infoMode] : null

  useEffect(() => {
    if (isCurrentNodeSplitting && splitMode) {
      setSelectedMode(splitMode)
    }
  }, [isCurrentNodeSplitting, splitMode])

  useEffect(() => {
    if (!infoMode) {
      return undefined
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setInfoMode(null)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [infoMode])


  useEffect(() => {
    if (isCurrentNodeSplitting) {
      wasCurrentNodeSplittingRef.current = true
      return
    }

    if (!wasCurrentNodeSplittingRef.current) {
      return
    }

    if (splitStatus === 'idle') {
      wasCurrentNodeSplittingRef.current = false
      void loadDetailState(projectId, node.node_id).catch(() => undefined)
      navigate('/graph', { state: { revealSplitNodeId: node.node_id } })
      return
    }

    if (splitStatus === 'failed') {
      wasCurrentNodeSplittingRef.current = false
    }
  }, [isCurrentNodeSplitting, loadDetailState, navigate, node.node_id, projectId, splitStatus])

  function handleInfoBackdropClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      setInfoMode(null)
    }
  }

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
    <div className={`${styles.splitPanel} ${styles.documentPanel}`}>
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

      {isCurrentNodeSplitting ? (
        <div
          className={`${styles.editorGeneratingBody} ${styles.splitGeneratingBody}`}
          data-testid="split-generating"
        >
          <AgentSpinner words={SPINNER_WORDS_SPLITTING} />
        </div>
      ) : (
        <>
          {!canConfirmSplit || isAnySplitActive ? (
            <div className={styles.splitHintPanel} data-testid="split-readiness-hint">
              <p className={styles.body}>
                {splitConfirmed
                  ? 'This node has already been split.'
                  : !canConfirmSplit
                    ? 'Confirm the latest frame first. Once the updated frame is confirmed and clarify is clear, you can choose a split mode here.'
                    : 'A split is already running for this project. Wait for it to finish before starting another one.'}
              </p>
            </div>
          ) : null}

          <div className={styles.splitOptionsGroup} role="radiogroup" aria-label="Split modes">
            {GRAPH_SPLIT_OPTIONS.map((option) => {
              const selected = option.id === selectedMode
              return (
                <div key={option.id} className={styles.splitOptionShell}>
                  <button
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
                  <button
                    type="button"
                    className={styles.splitOptionInfoButton}
                    data-testid={`split-option-info-${option.id}`}
                    aria-label={`Show ${option.label} split mode info`}
                    onClick={() => setInfoMode(option.id)}
                  >
                    i
                  </button>
                </div>
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
              Confirm
            </button>
          </div>
        </>
      )}

      {infoOption && infoContent ? (
        <div
          className={styles.splitInfoOverlay}
          data-testid="split-info-overlay"
          role="presentation"
          onClick={handleInfoBackdropClick}
        >
          <section
            className={styles.splitInfoDialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby="split-info-title"
          >
            <div className={styles.splitInfoHeader}>
              <div>
                <p className={styles.eyebrow}>Mode info</p>
                <h3 id="split-info-title" className={styles.title}>
                  {infoOption.label}
                </h3>
              </div>
              <button
                type="button"
                className={styles.splitInfoCloseButton}
                aria-label="Close split mode info"
                onClick={() => setInfoMode(null)}
              >
                x
              </button>
            </div>

            <div className={styles.splitInfoBody}>
              <section className={styles.splitInfoSection}>
                <h4>Original task</h4>
                <p>{SPLIT_MODE_ORIGINAL_TASK}</p>
              </section>

              <section className={styles.splitInfoSection}>
                <h4>Mode description</h4>
                <p>{infoContent.modeDescription}</p>
              </section>

              <section className={styles.splitInfoSection}>
                <h4>Subtasks</h4>
                <ol className={styles.splitInfoSubtaskList}>
                  {infoContent.subtasks.map((subtask) => (
                    <li key={subtask.title}>
                      <strong>{subtask.title}</strong>
                      <p>{subtask.body}</p>
                    </li>
                  ))}
                </ol>
              </section>

              <section className={styles.splitInfoSection}>
                <h4>Brief explain</h4>
                <p>{infoContent.briefExplain}</p>
              </section>

              <section className={styles.splitInfoSection}>
                <h4>When it works best</h4>
                <p>{infoContent.whenItWorksBest}</p>
              </section>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
