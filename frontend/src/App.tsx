import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { BreadcrumbPlaceholder } from './features/breadcrumb/BreadcrumbPlaceholder'
import { BreadcrumbPlaceholderV2 } from './features/conversation/BreadcrumbPlaceholderV2'
import { GraphWorkspace } from './features/graph/GraphWorkspace'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<GraphWorkspace />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat"
            element={<BreadcrumbPlaceholder />}
          />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat-v2"
            element={<BreadcrumbPlaceholderV2 />}
          />
          <Route path="*" element={<Navigate replace to="/" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
