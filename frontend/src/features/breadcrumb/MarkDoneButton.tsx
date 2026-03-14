import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import type { NodeRecord } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import styles from './MarkDoneButton.module.css'

type Props = {
  projectId: string
  nodeId: string
  node: NodeRecord
}

export function MarkDoneButton({ projectId, nodeId, node }: Props) {
  const navigate = useNavigate()
  const completeNode = useProjectStore((state) => state.completeNode)
  const isCompletingNode = useProjectStore((state) => state.isCompletingNode)
  const snapshot = useProjectStore((state) => state.snapshot)

  const canMarkDone = useMemo(() => {
    if (!snapshot || snapshot.project.id !== projectId || node.is_superseded) {
      return false
    }
    if (!(node.phase === 'ready_for_execution' || node.phase === 'executing')) {
      return false
    }
    const activeChildren = node.child_ids
      .map(
        (childId) => snapshot.tree_state.node_registry.find((item) => item.node_id === childId) ?? null,
      )
      .filter((child) => child && !child.is_superseded)
    return activeChildren.length === 0 && (node.status === 'ready' || node.status === 'in_progress')
  }, [node.child_ids, node.is_superseded, node.phase, node.status, projectId, snapshot])

  return (
    <button
      className={styles.button}
      type="button"
      disabled={!canMarkDone || isCompletingNode}
      onClick={async () => {
        if (!canMarkDone || isCompletingNode) {
          return
        }
        try {
          await completeNode(nodeId)
          navigate('/')
        } catch {
          return
        }
      }}
    >
      {isCompletingNode ? 'Marking Done...' : 'Mark Done'}
    </button>
  )
}
