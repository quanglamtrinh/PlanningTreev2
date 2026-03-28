import type { NodeRecord } from '../../api/types'

// ─── Layout constants (vertical tree: root top → children below, siblings left–right) ───
// Vertical distance between depth levels (parent row → child row). This is the primary control for
// “more air” between tiers — increase here for height only (sibling packing on X is unchanged).
// Budget: tallest parent (~300px) + gapAbove(28) + reviewCard(320) + gapBelow(72) = 720px min.
// 860px gives ~140px breathing room above that worst case.
const DEPTH_STEP_PX = 860

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
 * Worst-case height of the review card for layout purposes.
 * Breakdown for up to 6 sibling rows + wrapping subtitle + footer button:
 *   padding(26) + flex-gaps(36) + eyebrow(12) + title(18) + subtitle(36, 2 lines)
 *   + stats(14) + manifest-header(11) + 6 rows×14px(84) + row-gaps(15) + footer(42) ≈ 294px.
 * Use 320 to add a buffer for edge cases (very long parent titles, extra stats).
 */
const REVIEW_CARD_HEIGHT_PX = 320

/** Minimum gap between parent bottom and the top of the review card. */
const MIN_REVIEW_GAP_ABOVE_PX = 28

/**
 * Minimum gap between the bottom of the review card and the top of the child row (tasks below).
 * Larger than {@link MIN_REVIEW_GAP_ABOVE_PX} so the review strip sits clearly above children.
 */
const MIN_REVIEW_GAP_BELOW_PX = 72

/** Matches `GraphNode` card width (`GraphNode.module.css` `.card`). */
export const GRAPH_NODE_WIDTH_PX = 270

/** Matches `GraphNode` `.wrapper` `margin-bottom` (space below each node in the canvas). */
export const GRAPH_NODE_MARGIN_BOTTOM_PX = 10

/** Matches `ReviewGraphNode` card width (`ReviewGraphNode.module.css`). */
export const REVIEW_NODE_WIDTH_PX = 220

// Width of one horizontal "unit" in pixels. Subtree width is measured in these
// units (same packing math as before, applied on X for siblings).
const HORIZONTAL_UNIT_PX = 28

/** Minimum horizontal units so a 270px graph card fits in one sibling slot when ghosts are present. */
const GRAPH_NODE_SPAN_UNITS = Math.ceil(GRAPH_NODE_WIDTH_PX / HORIZONTAL_UNIT_PX)

// Every node occupies at least this many units of vertical space, regardless
// of how short its text is. Keeps leaf nodes a comfortable height.
const MIN_NODE_SPAN_UNITS = 7

// Extra units of blank space inserted BETWEEN siblings so they never
// visually touch. This is the primary gap control. 2 units = 56px visible gap between cards.
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

export type GhostSiblingLayoutEntry = { id: string }

export function buildTreeLayoutPositions({
  nodeById,
  rootIds,
  visibleChildrenById,
  depthBaseNodeId,
  ghostSiblingsByParent,
}: {
  nodeById: Map<string, NodeRecord>
  rootIds: string[]
  visibleChildrenById: Map<string, string[]>
  /** When set, horizontal position uses depth relative to this node (subtree “view root”). */
  depthBaseNodeId?: string | null
  /** Pending sibling placeholders: same horizontal row as real children under each parent. */
  ghostSiblingsByParent?: Map<string, GhostSiblingLayoutEntry[]>
}) {
  const baseDepth =
    depthBaseNodeId && nodeById.has(depthBaseNodeId) ? (nodeById.get(depthBaseNodeId)?.depth ?? 0) : 0

  const subtreeUnits = new Map<string, number>()
  const nodePositions = new Map<string, { x: number; y: number }>()
  const ghostPositions = new Map<string, { x: number; y: number }>()

  // Compute how many stack units a subtree rooted at nodeId needs (sibling axis).
  // For leaf nodes this equals the node's capped horizontal footprint (see ownUnits).
  // For parents: row width is the sum of each child's subtree width (+ ghosts + gaps). Siblings are
  // not forced to match the widest branch — avoids one deep subtree spacing out an entire row
  // (e.g. Bookstore root → five tasks where only one has children).
  const computeUnits = (nodeId: string): number => {
    const cached = subtreeUnits.get(nodeId)
    if (cached !== undefined) {
      return cached
    }
    const node = nodeById.get(nodeId)
    if (!node) {
      return MIN_NODE_SPAN_UNITS
    }
    // Cap horizontal span: tall descriptions used to inflate “units” and spread siblings apart.
    // Graph cards are fixed ~270px wide; packing uses that width, not pixel height of body text.
    const rawOwnUnits = Math.ceil(estimateNodeHeight(node) / HORIZONTAL_UNIT_PX)
    const ownUnits = Math.min(
      GRAPH_NODE_SPAN_UNITS,
      Math.max(MIN_NODE_SPAN_UNITS, rawOwnUnits),
    )
    const children = visibleChildrenById.get(nodeId) ?? []
    const ghostExtra = ghostSiblingsByParent?.get(nodeId)?.length ?? 0

    if (children.length === 0) {
      if (ghostExtra === 0) {
        subtreeUnits.set(nodeId, ownUnits)
        return ownUnits
      }
      const slot = Math.max(MIN_NODE_SPAN_UNITS, GRAPH_NODE_SPAN_UNITS)
      const childCount = ghostExtra
      const totalGaps = SIBLING_GAP_UNITS * Math.max(0, childCount - 1)
      const childrenBlock = slot * childCount + totalGaps
      const total = Math.max(ownUnits, childrenBlock)
      subtreeUnits.set(nodeId, total)
      return total
    }

    const ghostW = Math.max(MIN_NODE_SPAN_UNITS, GRAPH_NODE_SPAN_UNITS)
    const childWidths = children.map((id) => computeUnits(id))
    const childCount = children.length + ghostExtra
    const totalGaps = SIBLING_GAP_UNITS * Math.max(0, childCount - 1)
    const childrenBlock =
      childWidths.reduce((sum, w) => sum + w, 0) + ghostExtra * ghostW + totalGaps
    const total = Math.max(ownUnits, childrenBlock)
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
    nodePositions.set(nodeId, {
      x: centerX - GRAPH_NODE_WIDTH_PX / 2,
      y: Math.max(0, node.depth - baseDepth) * DEPTH_STEP_PX,
    })

    const children = visibleChildrenById.get(nodeId) ?? []
    const ghostList = ghostSiblingsByParent?.get(nodeId) ?? []
    const ghostExtra = ghostList.length
    const childDepthY = Math.max(0, node.depth - baseDepth + 1) * DEPTH_STEP_PX

    if (children.length === 0 && ghostExtra === 0) {
      return
    }

    if (children.length === 0 && ghostExtra > 0) {
      const slot = Math.max(MIN_NODE_SPAN_UNITS, GRAPH_NODE_SPAN_UNITS)
      const childCount = ghostExtra
      const totalGaps = SIBLING_GAP_UNITS * Math.max(0, childCount - 1)
      const childrenBlock = slot * childCount + totalGaps
      let cursor = startUnit + Math.max(0, (nodeUnits - childrenBlock) / 2)
      for (let g = 0; g < ghostExtra; g++) {
        const centerUnit = cursor + slot / 2
        ghostPositions.set(ghostList[g].id, {
          x: centerUnit * HORIZONTAL_UNIT_PX - GRAPH_NODE_WIDTH_PX / 2,
          y: childDepthY,
        })
        cursor += slot + SIBLING_GAP_UNITS
      }
      return
    }

    const ghostW = Math.max(MIN_NODE_SPAN_UNITS, GRAPH_NODE_SPAN_UNITS)
    const childWidths = children.map((id) => computeUnits(id))
    const childCount = children.length + ghostExtra
    const totalGaps = SIBLING_GAP_UNITS * Math.max(0, childCount - 1)
    const childrenBlock =
      childWidths.reduce((sum, w) => sum + w, 0) + ghostExtra * ghostW + totalGaps

    let cursor = startUnit + Math.max(0, (nodeUnits - childrenBlock) / 2)
    for (let i = 0; i < children.length; i++) {
      const childId = children[i]
      const w = childWidths[i]
      assign(childId, cursor)
      cursor += w + SIBLING_GAP_UNITS
    }
    for (let g = 0; g < ghostExtra; g++) {
      const centerUnit = cursor + ghostW / 2
      ghostPositions.set(ghostList[g].id, {
        x: centerUnit * HORIZONTAL_UNIT_PX - GRAPH_NODE_WIDTH_PX / 2,
        y: childDepthY,
      })
      cursor += ghostW + SIBLING_GAP_UNITS
    }
  }

  let offset = 0
  for (const rootId of rootIds) {
    assign(rootId, offset)
    // Extra gap between separate root trees
    offset += computeUnits(rootId) + SIBLING_GAP_UNITS * 2
  }

  return { nodePositions, ghostPositions }
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
    if (childIds.length === 0) {
      continue
    }

    const parentRecord = nodeById.get(parentId)
    if (!parentRecord) {
      continue
    }

    // Use real review_node_id if the parent has one; fall back to synthetic for legacy 2+ child trees.
    const reviewNodeId = parentRecord.review_node_id
    const useSynthetic = !reviewNodeId && childIds.length >= 2
    if (!reviewNodeId && !useSynthetic) {
      continue
    }

    const parentPosition = treePositions.get(parentId)
    if (!parentPosition) {
      continue
    }

    const directChildYs = childIds
      .map((childId) => treePositions.get(childId)?.y)
      .filter((value): value is number => typeof value === 'number')
    if (directChildYs.length === 0) {
      continue
    }

    const parentY = parentPosition.y
    const parentBottom = parentY + estimateNodeHeight(parentRecord) + GRAPH_NODE_MARGIN_BOTTOM_PX
    const childrenTop = Math.min(...directChildYs)

    // Place review at 30% of the way from parent-bottom to child-top so it reads as
    // clearly below the parent without consuming half the vertical band.
    // Centre the review card in the band between parent-bottom and children-top.
    // Clamped so it never overlaps parent (MIN_REVIEW_GAP_ABOVE_PX) or children (MIN_REVIEW_GAP_BELOW_PX).
    const preferred = (parentBottom + childrenTop) / 2 - REVIEW_CARD_HEIGHT_PX / 2
    const reviewY = Math.min(
      Math.max(preferred, parentBottom + MIN_REVIEW_GAP_ABOVE_PX),
      childrenTop - REVIEW_CARD_HEIGHT_PX - MIN_REVIEW_GAP_BELOW_PX,
    )

    const id = reviewNodeId ?? `review::${parentId}`
    reviewPositions.set(id, {
      x: parentPosition.x + (GRAPH_NODE_WIDTH_PX - REVIEW_NODE_WIDTH_PX) / 2,
      y: reviewY,
    })
  }

  return reviewPositions
}
