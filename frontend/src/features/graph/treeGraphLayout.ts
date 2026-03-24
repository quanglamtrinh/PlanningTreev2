import type { NodeRecord } from '../../api/types'

// ─── Layout constants (vertical tree: root top → children below, siblings left–right) ───
// Vertical distance between depth levels (parent row → child row).
// Must be large enough that parent card (up to ~260px) + review card (96px) + 2×MIN_REVIEW_GAP
// all fit comfortably. At 560px: even a 260px parent leaves 300px for review+gaps (102px each).
const DEPTH_STEP_PX = 560

/** Exported for TreeGraph position fallback when layout map misses a node. */
export const TREE_DEPTH_STEP_PX = DEPTH_STEP_PX

/**
 * @deprecated Kept for test compatibility — review Y is now computed as the midpoint between
 * parent bottom and children top. This value is no longer used in the layout logic.
 */
export const REVIEW_PARENT_GAP_PX = 0

/**
 * @deprecated No longer used for review Y. Kept for tests/docs tuning.
 */
export const REVIEW_CHILD_TOP_CLEARANCE_PX = 152

/**
 * Estimated height of the review card (eyebrow + title + subtitle + padding).
 * Used to vertically center the review card in the gap between parent and children.
 */
const REVIEW_CARD_HEIGHT_PX = 96

/**
 * Minimum breathing room above and below the review card within the parent→children gap.
 */
const MIN_REVIEW_GAP_PX = 48

/** Matches `GraphNode` card width (`GraphNode.module.css` `.card`). */
export const GRAPH_NODE_WIDTH_PX = 270

/** Matches `GraphNode` `.wrapper` `margin-bottom` (space below each node in the canvas). */
export const GRAPH_NODE_MARGIN_BOTTOM_PX = 10

/** Matches `ReviewGraphNode` card width (`ReviewGraphNode.module.css`). */
export const REVIEW_NODE_WIDTH_PX = 220

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
    const centerX = (startUnit + nodeUnits / 2) * HORIZONTAL_UNIT_PX
    positions.set(nodeId, {
      x: centerX - GRAPH_NODE_WIDTH_PX / 2,
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
    const parentBottom = parentY + estimateNodeHeight(parentRecord) + GRAPH_NODE_MARGIN_BOTTOM_PX

    // Top edge of the children row (min Y across all visible direct children).
    const childrenTop = Math.min(...directChildYs)

    // Place review card vertically centered in the gap between parent bottom and children top,
    // but always keep at least MIN_REVIEW_GAP_PX of breathing room on each side.
    const midpoint = (parentBottom + childrenTop) / 2
    const reviewY = Math.min(
      Math.max(
        midpoint - REVIEW_CARD_HEIGHT_PX / 2,
        parentBottom + MIN_REVIEW_GAP_PX,
      ),
      childrenTop - REVIEW_CARD_HEIGHT_PX - MIN_REVIEW_GAP_PX,
    )

    reviewPositions.set(`review::${parentId}`, {
      // Center the narrower review card (220px) under the graph node (270px).
      x: parentPosition.x + (GRAPH_NODE_WIDTH_PX - REVIEW_NODE_WIDTH_PX) / 2,
      y: reviewY,
    })
  }

  return reviewPositions
}
