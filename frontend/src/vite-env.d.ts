/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOCK_DETAIL_STATE?: string
  readonly VITE_MOCK_GIT_SCENARIO?: string
  readonly VITE_MOCK_GIT_INIT_CTA?: string
}

declare module '*.module.css' {
  const classes: Record<string, string>
  export default classes
}
