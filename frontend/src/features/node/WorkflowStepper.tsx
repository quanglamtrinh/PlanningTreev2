import type { DetailState } from '../../api/types'
import styles from './WorkflowStepper.module.css'

export type WorkflowTab = 'describe' | 'frame' | 'clarify' | 'frame_updated' | 'split' | 'spec'

type WorkflowStepperProps = {
  detailTab: WorkflowTab
  detailState: DetailState | undefined
  onTabChange: (tab: WorkflowTab) => void
  /** After Frame updated: spec path disables Split; split path disables Spec + Finish Task. */
  tabDisabled?: { spec?: boolean; split?: boolean; finish?: boolean }
  /** When true, shows progress only; use document tabs (breadcrumb) to change views. */
  readOnly?: boolean
}

function TickIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle
        cx="8"
        cy="8"
        r="6.75"
        stroke="currentColor"
        strokeOpacity="0.45"
        strokeWidth="1.25"
        fill="rgba(255,255,255,0.12)"
      />
      <path
        d="M4.75 8.1 7.1 10.45 11.25 5.55"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ArrowConn({ gridArea }: { gridArea: string }) {
  return (
    <span className={styles.arrowConn} style={{ gridArea }} aria-hidden="true">
      <span className={styles.arrowLine} />
    </span>
  )
}

export function WorkflowStepper({
  detailTab,
  detailState,
  onTabChange,
  tabDisabled,
  readOnly = false,
}: WorkflowStepperProps) {
  const frameConfirmed = detailState?.frame_confirmed ?? false
  const clarifyConfirmed = detailState?.clarify_confirmed ?? false
  const specConfirmed = detailState?.spec_confirmed ?? false
  const frameBranchReady = detailState?.frame_branch_ready ?? false
  const frameUpdatedDone = frameBranchReady || detailState?.active_step === 'spec'

  const specDisabled = tabDisabled?.spec === true
  const splitDisabled = tabDisabled?.split === true
  const finishDisabled = tabDisabled?.finish === true

  const nodeClass = (id: WorkflowTab, doneOverride = false): string => {
    const done =
      doneOverride ||
      (id === 'frame'
        ? frameConfirmed
        : id === 'clarify'
          ? clarifyConfirmed
          : id === 'frame_updated'
            ? frameUpdatedDone
            : id === 'split'
              ? false
            : id === 'spec'
              ? specConfirmed
              : false)
    const active = !readOnly && detailTab === id
    return [styles.node, done ? styles.done : '', active ? styles.active : '']
      .filter(Boolean)
      .join(' ')
  }

  const nodeClassDisabled = (
    id: WorkflowTab,
    doneOverride = false,
    disabled?: boolean,
  ): string => {
    const base = nodeClass(id, doneOverride)
    return disabled ? `${base} ${styles.nodeDisabled}` : base
  }

  const stepAriaCurrent = (id: WorkflowTab) =>
    !readOnly && detailTab === id ? ('step' as const) : undefined

  return (
    <nav
      className={[styles.grid, readOnly ? styles.readOnly : ''].filter(Boolean).join(' ')}
      aria-label="Task workflow steps"
      aria-hidden={readOnly ? true : undefined}
      data-testid="workflow-stepper"
      data-stepper-mode={readOnly ? 'indicative' : 'interactive'}
    >
      <span
        className={styles.tj}
        style={{ gridColumn: '8', gridRow: '1 / 4' }}
        aria-hidden="true"
      />

      <ArrowConn gridArea="csArr" />

      <button
        type="button"
        className={nodeClassDisabled('spec', false, specDisabled)}
        style={{ gridArea: 'spec' }}
        disabled={specDisabled}
        tabIndex={readOnly ? -1 : undefined}
        onClick={
          readOnly || specDisabled
            ? undefined
            : () => {
                onTabChange('spec')
              }
        }
        aria-current={stepAriaCurrent('spec')}
        aria-disabled={specDisabled}
        title={specDisabled ? 'Unavailable after choosing Split from Frame updated' : undefined}
      >
        <span>Spec</span>
        {specConfirmed ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="cfArr2" />

      <span
        className={[
          styles.nodeVisual,
          specConfirmed ? styles.done : '',
          finishDisabled ? styles.nodeDisabled : '',
        ]
          .filter(Boolean)
          .join(' ')}
        style={{ gridArea: 'finish' }}
        aria-hidden="true"
        aria-disabled={finishDisabled}
        title={finishDisabled ? 'Unavailable after choosing Split from Frame updated' : undefined}
      >
        <span>Finish Task</span>
        {specConfirmed ? <TickIcon /> : null}
      </span>

      <button
        type="button"
        className={nodeClass('frame')}
        style={{ gridArea: 'frame' }}
        tabIndex={readOnly ? -1 : undefined}
        onClick={readOnly ? undefined : () => onTabChange('frame')}
        aria-current={stepAriaCurrent('frame')}
      >
        <span>Frame</span>
        {frameConfirmed ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="cfArr" />

      <button
        type="button"
        className={nodeClass('clarify')}
        style={{ gridArea: 'clarify' }}
        tabIndex={readOnly ? -1 : undefined}
        onClick={readOnly ? undefined : () => onTabChange('clarify')}
        aria-current={stepAriaCurrent('clarify')}
      >
        <span>Clarify</span>
        {clarifyConfirmed ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="doneArr" />

      <button
        type="button"
        className={nodeClass('frame_updated')}
        style={{ gridArea: 'frameUpd' }}
        tabIndex={readOnly ? -1 : undefined}
        onClick={readOnly ? undefined : () => onTabChange('frame_updated')}
        aria-current={stepAriaCurrent('frame_updated')}
      >
        <span>Frame Updated</span>
        {frameUpdatedDone ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="spArr" />

      <button
        type="button"
        className={nodeClassDisabled('split', false, splitDisabled)}
        style={{ gridArea: 'spTask' }}
        disabled={splitDisabled}
        tabIndex={readOnly ? -1 : undefined}
        onClick={
          readOnly || splitDisabled
            ? undefined
            : () => {
                onTabChange('split')
              }
        }
        aria-current={stepAriaCurrent('split')}
        aria-disabled={splitDisabled}
        title={splitDisabled ? 'Unavailable after choosing Create Spec from Frame updated' : undefined}
      >
        <span>Split</span>
      </button>
    </nav>
  )
}
