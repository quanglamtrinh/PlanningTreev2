import { afterEach, describe, expect, it } from 'vitest'

import type { BootstrapStatus } from '../../src/api/types'
import {
  isExecutionAuditV2SurfaceEnabled,
  isAuditUiuxV3FrontendEnabled,
  isExecutionUiuxV3FrontendEnabled,
} from '../../src/features/conversation/surfaceRouting'

type MutableImportMetaEnv = {
  VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND?: string
  VITE_EXECUTION_UIUX_V3_FRONTEND?: string
  VITE_AUDIT_UIUX_V3_FRONTEND?: string
}

const originalEnv = {
  VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND: import.meta.env.VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND,
  VITE_EXECUTION_UIUX_V3_FRONTEND: import.meta.env.VITE_EXECUTION_UIUX_V3_FRONTEND,
  VITE_AUDIT_UIUX_V3_FRONTEND: import.meta.env.VITE_AUDIT_UIUX_V3_FRONTEND,
}

function setEnv(overrides: MutableImportMetaEnv) {
  const env = import.meta.env as MutableImportMetaEnv
  env.VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND = overrides.VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND
  env.VITE_EXECUTION_UIUX_V3_FRONTEND = overrides.VITE_EXECUTION_UIUX_V3_FRONTEND
  env.VITE_AUDIT_UIUX_V3_FRONTEND = overrides.VITE_AUDIT_UIUX_V3_FRONTEND
}

function makeBootstrap(overrides: Partial<BootstrapStatus> = {}): BootstrapStatus {
  return {
    ready: true,
    workspace_configured: true,
    codex_available: true,
    codex_path: 'codex',
    execution_audit_v2_enabled: true,
    ...overrides,
  }
}

afterEach(() => {
  setEnv({
    VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND: originalEnv.VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND,
    VITE_EXECUTION_UIUX_V3_FRONTEND: originalEnv.VITE_EXECUTION_UIUX_V3_FRONTEND,
    VITE_AUDIT_UIUX_V3_FRONTEND: originalEnv.VITE_AUDIT_UIUX_V3_FRONTEND,
  })
})

describe('surfaceRouting lane-scoped V3 frontend flags', () => {
  it('treats unresolved bootstrap as V2-enabled during initial route hydration', () => {
    expect(isExecutionAuditV2SurfaceEnabled(null)).toBe(true)
    expect(isExecutionAuditV2SurfaceEnabled(undefined)).toBe(true)
  })

  it('uses lane-scoped bootstrap flags when present', () => {
    setEnv({})
    const bootstrap = makeBootstrap({
      execution_audit_uiux_v3_frontend_enabled: false,
      execution_uiux_v3_frontend_enabled: true,
      audit_uiux_v3_frontend_enabled: false,
    })

    expect(isExecutionUiuxV3FrontendEnabled(bootstrap)).toBe(true)
    expect(isAuditUiuxV3FrontendEnabled(bootstrap)).toBe(false)
  })

  it('falls back to shared bootstrap flag when lane-scoped fields are absent', () => {
    setEnv({})
    const bootstrap = makeBootstrap({
      execution_audit_uiux_v3_frontend_enabled: true,
    })

    expect(isExecutionUiuxV3FrontendEnabled(bootstrap)).toBe(true)
    expect(isAuditUiuxV3FrontendEnabled(bootstrap)).toBe(true)
  })

  it('uses lane env overrides before bootstrap values', () => {
    setEnv({
      VITE_EXECUTION_AUDIT_UIUX_V3_FRONTEND: '1',
      VITE_EXECUTION_UIUX_V3_FRONTEND: '0',
      VITE_AUDIT_UIUX_V3_FRONTEND: '1',
    })
    const bootstrap = makeBootstrap({
      execution_audit_uiux_v3_frontend_enabled: false,
      execution_uiux_v3_frontend_enabled: true,
      audit_uiux_v3_frontend_enabled: false,
    })

    expect(isExecutionUiuxV3FrontendEnabled(bootstrap)).toBe(false)
    expect(isAuditUiuxV3FrontendEnabled(bootstrap)).toBe(true)
  })
})
