import type { NodeRecord } from '../../api/types'

// ─── Layout constants (vertical tree: root top → children below, siblings left–right) ───
// Vertical distance between depth levels (parent row → child row).
// Tuned for org-chart–like edges. Large enough that parent + fixed-gap review + review card
// usually clears the child row (see buildReviewOverlayPositions).
const DEPTH_STEP_PX = 340

/** Exported for TreeGraph position fallback when layout map misses a node. */
export const TREE_DEPTH_STEP_PX = DEPTH_STEP_PX

/**
 * Vertical gap from the **bottom** of the parent card to the **top** of the review card.
 * Review `y` is always `parentBottom + REVIEW_PARENT_GAP_PX` (no mixing with child-row clamps).
 */
export const REVIEW_PARENT_GAP_PX = 48

/**
 * @deprecated No longer used for review Y (parent→review gap is fixed). Kept for tests/docs tuning.
 */
export const REVIEW_CHILD_TOP_CLEARANCE_PX = 152

// Width of one horizontal "unit" in pixels. Subtree width is measured in these
// units (same packing math as before, applied on X for siblings).
const HORIZONTAL_UNIT_PX = 28

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

/**
 * Height of the graph card in layout (matches `GraphNode`: title row + optional description, padding).
 * Title row shares width with status/actions (~140px); body text uses full card width.
 */
export function estimateNodeHeight(node: NodeRecord): number {
  const titleLines = estimateTextLines(node.title.trim(), 20)
  const desc = node.description.trim()
  const descLines = desc ? estimateTextLines(desc, 32) : 0
  const paddingY = 14 + 16
  const titleLinePx = 21
  const titleRowPx = Math.max(titleLines * titleLinePx, 26)
  const gapTitleToDesc = desc ? 8 : 0
  const descLinePx = 18
  return paddingY + titleRowPx + gapTitleToDesc + descLines * descLinePx
}

export function buildTreeLayoutPositions({
  nodeById,
  rootIds,
  visibleChildrenById,
  depthBaseNodeId,
}: {
  nodeById: Map<string, NodeRecord>
  rootIds: string[]
  visibleChildrenById: Map<string, string[]>
  /** When set, horizontal position uses depth relative to this node (subtree “view root”). */
  depthBaseNodeId?: string | null
}) {
  const baseDepth =
    depthBaseNodeId && nodeById.has(depthBaseNodeId) ? (nodeById.get(depthBaseNodeId)?.depth ?? 0) : 0

  const subtreeUnits = new Map<string, number>()
  const positions = new Map<string, { x: number; y: number }>()

  // Compute how many stack units a subtree rooted at nodeId needs (sibling axis).
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
      Math.ceil(estimateNodeHeight(node) / HORIZONTAL_UNIT_PX),
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
      x: (startUnit + nodeUnits / 2) * HORIZONTAL_UNIT_PX,
      y: Math.max(0, node.depth - baseDepth) * DEPTH_STEP_PX,
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

export function buildReviewOverlayPositions({
  nodeById,
  visibleChildrenById,
  treePositions,
}: {
  nodeById: Map<string, NodeRecord>
  visibleChildrenById: Map<string, string[]>
  treePositions: Map<string, { x: number; y: number }>
}) {
  const reviewPositions = new Map<string, { x: number; y: number }>()

  for (const [parentId, childIds] of visibleChildrenById) {
    if (childIds.length < 2) {
      continue
    }

    const parentPosition = treePositions.get(parentId)
    const parentRecord = nodeById.get(parentId)
    if (!parentPosition || !parentRecord) {
      continue
    }

    const visibleChildCount = childIds.reduce(
      (count, childId) => count + (treePositions.has(childId) ? 1 : 0),
      0,
    )
    if (visibleChildCount < 2) {
      continue
    }

    const directChildYs = childIds
      .map((childId) => treePositions.get(childId)?.y)
      .filter((value): value is number => typeof value === 'number')
    if (directChildYs.length < 2) {
      continue
    }

    const parentY = parentPosition.y
    const parentBottom = parentY + estimateNodeHeight(parentRecord)
    // Fixed gap from parent card bottom → review card top (REVIEW_PARENT_GAP_PX).
    const reviewY = parentBottom + REVIEW_PARENT_GAP_PX

    reviewPositions.set(`review::${parentId}`, {
      // Tree layout centers the parent over its direct-child block, so the
      // parent's x-coordinate is already the block center we want for review.
      x: parentPosition.x,
      y: reviewY,
    })
  }

  return reviewPositions
}
