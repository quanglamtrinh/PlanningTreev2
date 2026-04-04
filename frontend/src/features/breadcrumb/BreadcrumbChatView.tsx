import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { buildChatV2Url } from '../conversation/surfaceRouting'

export function BreadcrumbChatView() {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()

  useEffect(() => {
    if (!projectId || !nodeId) {
      return
    }
    void navigate(buildChatV2Url(projectId, nodeId, 'ask'), { replace: true })
  }, [navigate, nodeId, projectId])

  return null
}
