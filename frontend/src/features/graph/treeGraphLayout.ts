import type { NodeRecord } from '../../api/types'

// ─── Layout constants (vertical tree: root top → children below, siblings left–right) ───
// Row Y is computed from actual card heights (see applyCompactRowYs): compact gap after parents
// without a review strip; full review band when the parent shows the review overlay.

/** Exported for TreeGraph position fallback when layout map misses a node. */
export const TREE_DEPTH_STEP_PX = 320

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
const REVIEW_CARD_HEIGHT_PX = 310

/** Minimum gap between parent bottom and the top of the review card. */
const MIN_REVIEW_GAP_ABOVE_PX = 200

/**
 * Minimum gap between the bottom of the review card and the top of the child row (tasks below).
 */
const MIN_REVIEW_GAP_BELOW_PX = 72

/** Vertical gap parent → child row when this parent does not host a review strip (single child, etc.). */
const SMALL_ROW_GAP_PX = 56

/** Extra air below the project init/root node down to its first task row (no review strip on that parent). */
const INIT_NODE_TO_CHILD_GAP_PX = 200

/** Reserved band below parent when a review card sits between parent and children (matches overlay math). */
const REVIEW_ROW_GAP_PX =
  MIN_REVIEW_GAP_ABOVE_PX + REVIEW_CARD_HEIGHT_PX + MIN_REVIEW_GAP_BELOW_PX

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
 * Matches `GraphNode` chrome: `.nodeMain` vertical padding, title row (with status/badge column),
 * optional description, and non-init breadcrumb footer. Keeps stacked rows from overlapping
 * (notably after tasks move to `done`, which still show the full card + footer).
 */
const NODE_MAIN_PADDING_Y = 44

/** Title row height ≈ max(wrapped title, collapse + status badge rail). */
const TITLE_ROW_MIN_PX = 28

/** Non-init nodes: `.footer` margin + padding + border + full-width breadcrumb button. */
const BREADCRUMB_FOOTER_BLOCK_PX = 50

/** Init node: matches `.wrapperFloatingMenu` padding-bottom (⚡ badge extends below card). */
const INIT_FLOATING_MENU_RESERVE_PX = 24

export function estimateNodeHeight(node: NodeRecord): number {
  const titleLines = estimateTextLines(node.title.trim(), 20)
  const desc = node.description.trim()
  const descLines = desc ? estimateTextLines(desc, 32) : 0
  const titleLinePx = 21
  const titleTextHeight = Math.max(titleLines * titleLinePx, 26)
  const titleRowPx = Math.max(titleTextHeight, TITLE_ROW_MIN_PX)
  const gapTitleToDesc = desc ? 8 : 0
  const descLinePx = 18
  const footerPx = node.is_init_node === true ? 0 : BREADCRUMB_FOOTER_BLOCK_PX
  const initReservePx = node.is_init_node === true ? INIT_FLOATING_MENU_RESERVE_PX : 0
  return NODE_MAIN_PADDING_Y + titleRowPx + gapTitleToDesc + descLines * descLinePx + footerPx + initReservePx
}

export type GhostSiblingLayoutEntry = { id: string }

/** Same eligibility as `buildReviewOverlayPositions` — review strip between parent and child row. */
function parentHasReviewOverlay(
  parentId: string,
  nodeById: Map<string, NodeRecord>,
  visibleChildrenById: Map<string, string[]>,
): boolean {
  const childIds = visibleChildrenById.get(parentId) ?? []
  if (childIds.length === 0) {
    return false
  }
  const parent = nodeById.get(parentId)
  if (!parent) {
    return false
  }
  const reviewNodeId = parent.review_node_id
  const useSynthetic = !reviewNodeId && childIds.length >= 2
  return Boolean(reviewNodeId || useSynthetic)
}

/**
 * Stack depth rows from measured card heights: tight gaps when no review strip, full band when needed.
 */
function applyCompactRowYs(
  nodeById: Map<string, NodeRecord>,
  nodePositions: Map<string, { x: number; y: number }>,
  ghostPositions: Map<string, { x: number; y: number }>,
  visibleChildrenById: Map<string, string[]>,
  ghostSiblingsByParent: Map<string, GhostSiblingLayoutEntry[]> | undefined,
  baseDepth: number,
) {
  const relDepth = (depth: number) => Math.max(0, depth - baseDepth)
  const maxRel = Math.max(
    0,
    ...[...nodePositions.keys()]
      .map((id) => nodeById.get(id))
      .filter((n): n is NodeRecord => n != null)
      .map((n) => relDepth(n.depth)),
  )

  const rowTop = new Map<number, number>()
  rowTop.set(0, 0)

  for (let d = 0; d < maxRel; d++) {
    const rowY = rowTop.get(d) ?? 0
    const parents = [...nodeById.values()].filter(
      (n) => relDepth(n.depth) === d && nodePositions.has(n.node_id),
    )
    let nextRowTop = 0
    for (const p of parents) {
      const childIds = visibleChildrenById.get(p.node_id) ?? []
      const ghostExtra = ghostSiblingsByParent?.get(p.node_id)?.length ?? 0
      if (childIds.length === 0 && ghostExtra === 0) {
        continue
      }
      const bottom = rowY + estimateNodeHeight(p) + GRAPH_NODE_MARGIN_BOTTOM_PX
      const hasReview = parentHasReviewOverlay(p.node_id, nodeById, visibleChildrenById)
      const gap = hasReview
        ? REVIEW_ROW_GAP_PX
        : p.is_init_node
          ? INIT_NODE_TO_CHILD_GAP_PX
          : SMALL_ROW_GAP_PX
      nextRowTop = Math.max(nextRowTop, bottom + gap)
    }
    rowTop.set(d + 1, nextRowTop)
  }

  for (const [id, pos] of nodePositions) {
    const node = nodeById.get(id)
    if (!node) {
      continue
    }
    pos.y = rowTop.get(relDepth(node.depth)) ?? 0
  }

  if (ghostSiblingsByParent) {
    for (const [parentId, ghosts] of ghostSiblingsByParent) {
      const parent = nodeById.get(parentId)
      if (!parent) {
        continue
      }
      const childRowY = rowTop.get(relDepth(parent.depth) + 1) ?? 0
      for (const g of ghosts) {
        const gp = ghostPositions.get(g.id)
        if (gp) {
          gp.y = childRowY
        }
      }
    }
  }
}

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
      y: 0,
    })

    const children = visibleChildrenById.get(nodeId) ?? []
    const ghostList = ghostSiblingsByParent?.get(nodeId) ?? []
    const ghostExtra = ghostList.length

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
          y: 0,
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
        y: 0,
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

  applyCompactRowYs(
    nodeById,
    nodePositions,
    ghostPositions,
    visibleChildrenById,
    ghostSiblingsByParent,
    baseDepth,
  )

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
