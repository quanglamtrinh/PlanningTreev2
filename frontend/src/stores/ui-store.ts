import { create } from 'zustand'

export type ThemeId = 'default' | 'warm-earth' | 'slate' | 'forest' | 'obsidian' | 'amethyst'
export type WorkspaceSurface = 'graph' | 'breadcrumb'

export interface ThemeOption {
  id: ThemeId
  label: string
  swatch: string
}

export const THEME_OPTIONS: ThemeOption[] = [
  { id: 'default', label: 'Default', swatch: '#111827' },
  { id: 'warm-earth', label: 'Warm Earth', swatch: '#b34e12' },
  { id: 'slate', label: 'Slate Pro', swatch: '#2d55b8' },
  { id: 'forest', label: 'Forest', swatch: '#1e6b45' },
  { id: 'obsidian', label: 'Obsidian', swatch: '#f0956a' },
  { id: 'amethyst', label: 'Amethyst', swatch: '#6340bf' },
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
