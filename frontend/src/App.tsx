import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { BreadcrumbPlaceholder } from './features/breadcrumb/BreadcrumbPlaceholder'
import { BreadcrumbPlaceholderV2 } from './features/conversation/BreadcrumbPlaceholderV2'
import { GraphWorkspace } from './features/graph/GraphWorkspace'
import { SessionConsoleV2 } from './features/session_v2/shell/SessionConsoleV2'
import { UsageSnapshotPage } from './features/usage-snapshot/UsageSnapshotPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate replace to="/graph" />} />
          <Route path="/graph" element={<GraphWorkspace />} />
          <Route path="/usage-snapshot" element={<UsageSnapshotPage />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat"
            element={<BreadcrumbPlaceholder />}
          />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={<BreadcrumbPlaceholderV2 />}
          />
          <Route path="/session-v2" element={<SessionConsoleV2 />} />
          <Route path="*" element={<Navigate replace to="/graph" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
