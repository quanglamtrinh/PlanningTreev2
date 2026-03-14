import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { BreadcrumbWorkspace } from './features/breadcrumb/BreadcrumbWorkspace'
import { GraphWorkspace } from './features/graph/GraphWorkspace'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<GraphWorkspace />} />
          <Route
            path="/projects/:projectId/nodes/:nodeId/chat"
            element={<BreadcrumbWorkspace />}
          />
          <Route path="*" element={<Navigate replace to="/" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
