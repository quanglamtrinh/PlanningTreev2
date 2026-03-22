import { create } from 'zustand'

export type ThemeId = 'default' | 'warm-earth' | 'slate' | 'forest' | 'obsidian' | 'amethyst'
export type WorkspaceSurface = 'graph' | 'breadcrumb'

export interface ThemeOption {
  id: ThemeId
  label: string
  swatch: string
}

export const THEME_OPTIONS: ThemeOption[] = [
  { id: 'default', label: 'Canvas', swatch: '#2563eb' },
  { id: 'warm-earth', label: 'Terracotta', swatch: '#c2410c' },
  { id: 'slate', label: 'Fjord', swatch: '#0ea5e9' },
  { id: 'forest', label: 'Moss', swatch: '#047857' },
  { id: 'obsidian', label: 'Graphite', swatch: '#0891b2' },
  { id: 'amethyst', label: 'Aurora', swatch: '#7c3aed' },
]

const THEME_KEY = 'planningtree.theme'

function readStoredTheme(): ThemeId {
  if (typeof window === 'undefined') {
    return 'default'
  }
  const value = window.localStorage.getItem(THEME_KEY)
  return (THEME_OPTIONS.find((theme) => theme.id === value)?.id ?? 'default') as ThemeId
}

type UIStoreState = {
  activeSurface: WorkspaceSurface
  theme: ThemeId
  setActiveSurface: (surface: WorkspaceSurface) => void
  setTheme: (theme: ThemeId) => void
}

export const useUIStore = create<UIStoreState>((set) => ({
  activeSurface: 'graph',
  theme: readStoredTheme(),
  setActiveSurface: (activeSurface) => set({ activeSurface }),
  setTheme: (theme) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_KEY, theme)
    }
    set({ theme })
  },
}))
