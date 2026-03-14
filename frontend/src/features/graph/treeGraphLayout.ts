import type { NodeRecord } from '../../api/types'

// ─── Layout constants ───────────────────────────────────────────────
// Horizontal distance between depth levels (parent → child column gap)
const HORIZONTAL_STEP_PX = 380

// Height of one vertical "unit" in pixels. All vertical spacing is measured
// in these units so the math stays integer-friendly.
const VERTICAL_UNIT_PX = 28

// Every node occupies at least this many units of vertical space, regardless
// of how short its text is. Keeps leaf nodes a comfortable height.
const MIN_NODE_SPAN_UNITS = 7

// Extra units of blank space inserted BETWEEN siblings so they never
// visually touch. This is the primary gap control.
const SIBLING_GAP_UNITS = 2
// ────────────────────────────────────────────────────────────────────

function estimateTextLines(value: string, charsPerLine: number): number {
  const normalized = value.trim()
  if (!normalized) {
    return 1
  }
  return normalized
    .split(/\r?\n/)
    .map((line) => Math.max(1, Math.ceil(line.trim().length / Math.max(charsPerLine, 8))))
    .reduce((sum, lines) => sum + lines, 0)
}

export function estimateNodeHeight(node: NodeRecord): number {
  const titleLines = estimateTextLines(node.title, 26)
  const descriptionLines = estimateTextLines(node.description, 32)
  return 80 + titleLines * 16 + Math.min(descriptionLines, 3) * 17
}

export function buildTreeLayoutPositions({
  nodeById,
  rootIds,
  visibleChildrenById,
}: {
  nodeById: Map<string, NodeRecord>
  rootIds: string[]
  visibleChildrenById: Map<string, string[]>
}) {
  const subtreeUnits = new Map<string, number>()
  const positions = new Map<string, { x: number; y: number }>()

  // Compute how many vertical units a subtree rooted at nodeId needs.
  // For leaf nodes this equals the node's own height (in units).
  // For parents it equals the sum of all children's subtree units
  // PLUS gaps between siblings.
  const computeUnits = (nodeId: string): number => {
    const cached = subtreeUnits.get(nodeId)
    if (cached !== undefined) {
      return cached
    }
    const node = nodeById.get(nodeId)
    if (!node) {
      return MIN_NODE_SPAN_UNITS
    }
    const ownUnits = Math.max(
      MIN_NODE_SPAN_UNITS,
      Math.ceil(estimateNodeHeight(node) / VERTICAL_UNIT_PX),
    )
    const children = visibleChildrenById.get(nodeId) ?? []
    if (children.length === 0) {
      subtreeUnits.set(nodeId, ownUnits)
      return ownUnits
    }

    // Sum child subtrees + gaps between siblings
    const childSubtreeSum = children.reduce((sum, childId) => sum + computeUnits(childId), 0)
    const totalGaps = SIBLING_GAP_UNITS * (children.length - 1)
    const total = Math.max(ownUnits, childSubtreeSum + totalGaps)
    subtreeUnits.set(nodeId, total)
    return total
  }

  const assign = (nodeId: string, startUnit: number) => {
    const node = nodeById.get(nodeId)
    if (!node) {
      return
    }

    const nodeUnits = computeUnits(nodeId)
    positions.set(nodeId, {
      x: node.depth * HORIZONTAL_STEP_PX,
      y: (startUnit + nodeUnits / 2) * VERTICAL_UNIT_PX,
    })

    const children = visibleChildrenById.get(nodeId) ?? []
    if (children.length === 0) {
      return
    }

    // Total space children + gaps actually occupy
    const childSubtreeSum = children.reduce((sum, childId) => sum + computeUnits(childId), 0)
    const totalGaps = SIBLING_GAP_UNITS * (children.length - 1)
    const childrenBlock = childSubtreeSum + totalGaps

    // Center the children block relative to the parent's allocated space
    let cursor = startUnit + Math.max(0, (nodeUnits - childrenBlock) / 2)
    for (const childId of children) {
      assign(childId, cursor)
      cursor += computeUnits(childId) + SIBLING_GAP_UNITS
    }
  }

  let offset = 0
  for (const rootId of rootIds) {
    assign(rootId, offset)
    // Extra gap between separate root trees
    offset += computeUnits(rootId) + SIBLING_GAP_UNITS * 2
  }

  return positions
}
