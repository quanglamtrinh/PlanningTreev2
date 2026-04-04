import type { DetailState } from '../../api/types'
import styles from './NodeDetailCard.module.css'
import type { WorkflowTab } from './WorkflowStepper'

export function breadcrumbActiveTabLabelId(tab: WorkflowTab): string {
  switch (tab) {
    case 'describe':
      return 'breadcrumb-tab-info'
    case 'frame':
    case 'frame_updated':
      return 'breadcrumb-tab-frame'
    case 'clarify':
      return 'breadcrumb-tab-clarify'
    case 'split':
      return 'breadcrumb-tab-split'
    case 'spec':
      return 'breadcrumb-tab-spec'
    default:
      return 'breadcrumb-tab-frame'
  }
}

type Props = {
  detailTab: WorkflowTab
  detailState: DetailState | undefined
  onTabChange: (tab: WorkflowTab) => void
  tabDisabled?: { spec?: boolean; split?: boolean; finish?: boolean }
  panelId: string
  /** Inside document grey toolbar row (with save status); omit standalone bar styling */
  embedded?: boolean
}

export function BreadcrumbDetailTabs({
  detailTab,
  detailState,
  onTabChange,
  tabDisabled,
  panelId,
  embedded = false,
}: Props) {
  const showSplit = Boolean(detailState?.frame_branch_ready || detailTab === 'split')
  const specDisabled = tabDisabled?.spec === true
  const splitDisabled = tabDisabled?.split === true

  const frameMdActive = detailTab === 'frame' || detailTab === 'frame_updated'

  const tabClass = (active: boolean, disabled?: boolean) =>
    [
      styles.breadcrumbDetailTab,
      active ? styles.breadcrumbDetailTabActive : '',
      disabled ? styles.breadcrumbDetailTabDisabled : '',
    ]
      .filter(Boolean)
      .join(' ')

  const onFrameMdClick = () => {
    if (detailState?.frame_branch_ready) {
      onTabChange('frame_updated')
    } else {
      onTabChange('frame')
    }
  }

  return (
    <div
      className={[styles.breadcrumbDetailTablist, embedded ? styles.breadcrumbDetailTablistEmbedded : '']
        .filter(Boolean)
        .join(' ')}
      role="tablist"
      aria-label="Task document sections"
    >
      <button
        type="button"
        role="tab"
        id="breadcrumb-tab-info"
        aria-selected={detailTab === 'describe'}
        aria-controls={panelId}
        className={tabClass(detailTab === 'describe')}
        onClick={() => onTabChange('describe')}
      >
        Info
      </button>
      <button
        type="button"
        role="tab"
        id="breadcrumb-tab-frame"
        aria-selected={frameMdActive}
        aria-controls={panelId}
        className={tabClass(frameMdActive)}
        onClick={onFrameMdClick}
      >
        Frame
      </button>
      <button
        type="button"
        role="tab"
        id="breadcrumb-tab-clarify"
        aria-selected={detailTab === 'clarify'}
        aria-controls={panelId}
        className={tabClass(detailTab === 'clarify')}
        onClick={() => onTabChange('clarify')}
      >
        Clarify
      </button>
      {showSplit ? (
        <button
          type="button"
          role="tab"
          id="breadcrumb-tab-split"
          aria-selected={detailTab === 'split'}
          aria-controls={panelId}
          className={tabClass(detailTab === 'split', splitDisabled)}
          disabled={splitDisabled}
          aria-disabled={splitDisabled}
          title={
            splitDisabled ? 'Unavailable after choosing Create Spec from Frame updated' : undefined
          }
          onClick={() => {
            if (!splitDisabled) onTabChange('split')
          }}
        >
          Split
        </button>
      ) : null}
      <button
        type="button"
        role="tab"
        id="breadcrumb-tab-spec"
        aria-selected={detailTab === 'spec'}
        aria-controls={panelId}
        className={tabClass(detailTab === 'spec', specDisabled)}
        disabled={specDisabled}
        aria-disabled={specDisabled}
        title={specDisabled ? 'Unavailable after choosing Split from Frame updated' : undefined}
        onClick={() => {
          if (!specDisabled) onTabChange('spec')
        }}
      >
        Spec
      </button>
    </div>
  )
}
