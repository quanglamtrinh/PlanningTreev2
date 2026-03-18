/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.PLANNINGTREE_BACKEND_PORT ?? process.env.PLANNINGTREE_PORT ?? '8000'
const backendTarget = `http://127.0.0.1:${backendPort}`

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/v1': backendTarget,
      '/v2': backendTarget,
      '/health': backendTarget,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/unit/setup.ts',
    include: ['tests/unit/**/*.test.ts', 'tests/unit/**/*.test.tsx'],
    exclude: ['tests/e2e/**'],
  },
})
