type NodeDisplayIndexInput = {
  hierarchical_number?: string | null
  is_init_node?: boolean | null
  node_kind?: string | null
}

export function formatNodeDisplayIndex(node: NodeDisplayIndexInput | null | undefined): string | null {
  if (!node) {
    return null
  }
  const value = String(node.hierarchical_number ?? '').trim()
  if (!value) {
    return null
  }
  if (node.is_init_node === true || node.node_kind === 'root') {
    return null
  }
  return value
}

export function formatNodeTitleWithIndex(node: NodeDisplayIndexInput & { title?: string | null; node_id?: string | null }): string {
  const displayIndex = formatNodeDisplayIndex(node)
  const title = String(node.title ?? '').trim()
  if (displayIndex && title) {
    return `${displayIndex} ${title}`
  }
  return title || displayIndex || String(node.node_id ?? '').trim() || 'Untitled node'
}
