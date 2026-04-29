type NodeDisplayIndexInput = {
  hierarchical_number?: string | null
  is_init_node?: boolean | null
  node_kind?: string | null
}

export function formatHierarchicalDisplayIndex(rawNumber: string | null | undefined): string | null {
  const value = String(rawNumber ?? '').trim()
  if (!value) {
    return null
  }
  const segments = value.split('.').map((segment) => segment.trim()).filter(Boolean)
  if (segments.length <= 1) {
    return null
  }
  return segments.slice(1).join('.') || null
}

export function formatNodeDisplayIndex(node: NodeDisplayIndexInput | null | undefined): string | null {
  if (!node || node.is_init_node === true || node.node_kind === 'root') {
    return null
  }
  return formatHierarchicalDisplayIndex(node.hierarchical_number)
}

export function formatNodeTitleWithIndex(node: NodeDisplayIndexInput & { title?: string | null; node_id?: string | null }): string {
  const displayIndex = formatNodeDisplayIndex(node)
  const title = String(node.title ?? '').trim()
  if (displayIndex && title) {
    return `${displayIndex} ${title}`
  }
  return title || displayIndex || String(node.node_id ?? '').trim() || 'Untitled node'
}
