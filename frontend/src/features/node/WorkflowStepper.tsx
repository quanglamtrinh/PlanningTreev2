import type { DetailState } from '../../api/types'
import styles from './WorkflowStepper.module.css'

export type WorkflowTab = 'describe' | 'frame' | 'clarify' | 'frame_updated' | 'split' | 'spec'

type WorkflowStepperProps = {
  detailTab: WorkflowTab
  detailState: DetailState | undefined
  onTabChange: (tab: WorkflowTab) => void
  /** After Frame updated: spec path disables Split; split path disables Spec + Finish Task. */
  tabDisabled?: { spec?: boolean; split?: boolean; finish?: boolean }
}

function TickIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
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
    const active = detailTab === id
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

  return (
    <nav className={styles.grid} aria-label="Task workflow steps">
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
        onClick={() => {
          if (!specDisabled) onTabChange('spec')
        }}
        aria-current={detailTab === 'spec' ? 'step' : undefined}
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
        className={nodeClass('describe', true)}
        style={{ gridArea: 'desc' }}
        onClick={() => onTabChange('describe')}
        aria-current={detailTab === 'describe' ? 'step' : undefined}
      >
        <span>Describe</span>
        <TickIcon />
      </button>

      <span className={styles.arrowShort} style={{ gridArea: 'a1' }} aria-hidden="true" />

      <button
        type="button"
        className={nodeClass('frame')}
        style={{ gridArea: 'frame' }}
        onClick={() => onTabChange('frame')}
        aria-current={detailTab === 'frame' ? 'step' : undefined}
      >
        <span>Frame</span>
        {frameConfirmed ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="cfArr" />

      <button
        type="button"
        className={nodeClass('clarify')}
        style={{ gridArea: 'clarify' }}
        onClick={() => onTabChange('clarify')}
        aria-current={detailTab === 'clarify' ? 'step' : undefined}
      >
        <span>Clarify</span>
        {clarifyConfirmed ? <TickIcon /> : null}
      </button>

      <ArrowConn gridArea="doneArr" />

      <button
        type="button"
        className={nodeClass('frame_updated')}
        style={{ gridArea: 'frameUpd' }}
        onClick={() => onTabChange('frame_updated')}
        aria-current={detailTab === 'frame_updated' ? 'step' : undefined}
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
        onClick={() => {
          if (!splitDisabled) onTabChange('split')
        }}
        aria-current={detailTab === 'split' ? 'step' : undefined}
        aria-disabled={splitDisabled}
        title={splitDisabled ? 'Unavailable after choosing Create Spec from Frame updated' : undefined}
      >
        <span>Split</span>
      </button>
    </nav>
  )
}
