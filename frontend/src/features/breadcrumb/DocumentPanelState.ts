import type { NodePhase, NodeRecord } from '../../api/types'

export function formatPhaseLabel(phase: NodePhase) {
  return phase.replace(/_/g, ' ')
}

export function isDocumentReadOnly(node: NodeRecord) {
  return (
    node.is_superseded ||
    node.status === 'done' ||
    node.phase === 'executing' ||
    node.phase === 'closed'
  )
}
