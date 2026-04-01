import { createContext, useContext, type ReactNode } from 'react'
import type { SplitMode } from '../../api/types'

export type GraphNodeActions = {
  selectNode: (nodeId: string) => void
  toggleCollapse: (nodeId: string) => void
  createChild: (nodeId: string) => void
  split: (nodeId: string, mode: SplitMode) => void
  openBreadcrumb: (nodeId: string) => void
  infoClick: (nodeId: string) => void
  graphViewRootId: string | null
  setGraphViewRoot: (nodeId: string | null) => void
}

const GraphNodeActionsContext = createContext<GraphNodeActions | null>(null)

export function GraphNodeActionsProvider({
  value,
  children,
}: {
  value: GraphNodeActions
  children: ReactNode
}) {
  return <GraphNodeActionsContext.Provider value={value}>{children}</GraphNodeActionsContext.Provider>
}

export function useGraphNodeActions(): GraphNodeActions {
  const ctx = useContext(GraphNodeActionsContext)
  if (!ctx) {
    throw new Error('useGraphNodeActions must be used under GraphNodeActionsProvider')
  }
  return ctx
}
