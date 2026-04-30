import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { BreadcrumbViewV2 } from './features/conversation/BreadcrumbViewV2'
import { ExtensionsPage } from './features/extensions/ExtensionsPage'
import { SkillsPage } from './features/skills/SkillsPage'
import { GraphWorkspace } from './features/graph/GraphWorkspace'
import { SessionConsoleV2 } from './features/session_v2/shell/SessionConsoleV2'
import { UsageSnapshotPage } from './features/usage-snapshot/UsageSnapshotPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate replace to="/session-v2" />} />
          <Route path="/graph" element={<GraphWorkspace />} />
          <Route path="/extensions" element={<ExtensionsPage />} />
          <Route path="/skills" element={<SkillsPage />} />
          <Route path="/usage-snapshot" element={<UsageSnapshotPage />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat"
            element={<BreadcrumbViewV2 />}
          />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={<BreadcrumbViewV2 />}
          />
          <Route path="/session-v2" element={<SessionConsoleV2 />} />
          <Route path="*" element={<Navigate replace to="/session-v2" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
