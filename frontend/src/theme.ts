import type { AppSettings } from './api/types'

export type ThemeId = AppSettings['theme']

/** The colours a theme is judged on. These mirror the matching block in
 *  styles/global.css; theme.test.ts fails if the two drift, so a palette edit cannot
 *  quietly skip the contrast check. They also paint the swatches in Settings, which
 *  have to show a theme that is not the one currently applied. */
export interface ThemePalette {
  bg: string
  bgElev: string
  bgElev2: string
  border: string
  text: string
  textDim: string
  accent: string
  onAccent: string
  danger: string
}

export interface ThemeInfo {
  id: ThemeId
  label: string
  blurb: string
  palette: ThemePalette
}

export const DEFAULT_THEME: ThemeId = 'midnight'

export const THEMES: readonly ThemeInfo[] = [
  {
    id: 'midnight',
    label: 'Midnight',
    blurb: 'Dark navy. The original look.',
    palette: {
      bg: '#0f172a',
      bgElev: '#1e293b',
      bgElev2: '#334155',
      border: '#334155',
      text: '#f1f5f9',
      textDim: '#a3b1c6',
      accent: '#38bdf8',
      onAccent: '#06283a',
      danger: '#f87171',
    },
  },
  {
    id: 'daylight',
    label: 'Daylight',
    blurb: 'Warm paper and dark ink, for a bright kitchen.',
    palette: {
      bg: '#f6f1e7',
      bgElev: '#fcf9f2',
      bgElev2: '#e9e1d0',
      border: '#857d6c',
      text: '#1c1a16',
      textDim: '#51493d',
      accent: '#0369a1',
      onAccent: '#ffffff',
      danger: '#b91c1c',
    },
  },
  {
    id: 'hearth',
    label: 'Hearth',
    blurb: 'Warm charcoal and amber, easy on a dim room at night.',
    palette: {
      bg: '#1c1613',
      bgElev: '#2a211c',
      bgElev2: '#3a2e27',
      border: '#7d6b5c',
      text: '#f5ebdc',
      textDim: '#c4b3a0',
      accent: '#e8a24a',
      onAccent: '#2a1503',
      danger: '#ff8f7d',
    },
  },
]

export function isThemeId(value: unknown): value is ThemeId {
  return THEMES.some((t) => t.id === value)
}

function channel(hex: string, offset: number): number {
  const c = parseInt(hex.slice(offset, offset + 2), 16) / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5)
}

/** WCAG 2.x contrast ratio between two `#rrggbb` colours, from 1 to 21. */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// Read by the inline script in index.html as well; keep the key in step with it.
const STORAGE_KEY = 'mantel.theme'

/** Points the whole app at a theme. Also remembers it on this device so the next load
 *  paints the right colours before the settings request has come back -- without that,
 *  a Daylight wall display flashes navy every time it reloads. */
export function applyTheme(id: ThemeId): void {
  document.documentElement.dataset.theme = id
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Private windows and blocked site data throw; the theme still applies, it just
    // will not be remembered for the first paint.
  }
  const t = THEMES.find((x) => x.id === id)
  // The browser chrome and the installed-app title bar take their colour from here.
  if (t) document.querySelector('meta[name="theme-color"]')?.setAttribute('content', t.palette.bg)
}
