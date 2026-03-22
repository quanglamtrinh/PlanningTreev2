import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { initAuthToken } from './api/client'

async function bootstrap() {
  await initAuthToken()
  const root = document.getElementById('root')
  if (!root) throw new Error('Root element not found')

  createRoot(root).render(
    <StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </StrictMode>,
  )
}

bootstrap().catch((err) => {
  const root = document.getElementById('root')
  if (root) {
    root.innerHTML = `
      <div style="padding:2rem;font-family:system-ui,sans-serif;color:#c00">
        <h2>PlanningTree failed to start</h2>
        <p>${err instanceof Error ? err.message : String(err)}</p>
        <p style="color:#666;font-size:0.9rem">
          Try restarting the application. If this persists, check the console for details.
        </p>
      </div>
    `
  }
  console.error('Bootstrap failed:', err)
})
