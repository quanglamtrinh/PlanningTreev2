import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  readyState = 0
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  close() {
    this.readyState = 2
  }

  emitOpen() {
    this.onopen?.(new Event('open'))
  }

  emitMessage(data: string) {
    this.onmessage?.({ data } as MessageEvent<string>)
  }

  emitError() {
    this.onerror?.(new Event('error'))
  }

  static reset() {
    MockEventSource.instances = []
  }
}

vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource)
vi.stubGlobal('navigator', {
  ...globalThis.navigator,
  clipboard: {
    writeText: vi.fn(async () => undefined),
  },
})
vi.stubGlobal(
  'matchMedia',
  vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
)

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  MockEventSource.reset()
})
