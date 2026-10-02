import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { THEMES, contrastRatio, isThemeId, type ThemePalette } from './theme'

const css = readFileSync(new URL('./styles/global.css', import.meta.url), 'utf8')

/** The declarations of one theme's block; midnight is the bare `:root`. */
function block(id: string): string {
  const selector = id === 'midnight' ? ':root {' : `:root[data-theme='${id}'] {`
  const start = css.indexOf(selector)
  expect(start, `global.css has no block for ${id}`).toBeGreaterThanOrEqual(0)
  return css.slice(start, css.indexOf('\n}', start))
}

const TOKENS: Record<keyof ThemePalette, string> = {
  bg: '--bg',
  bgElev: '--bg-elev',
  bgElev2: '--bg-elev-2',
  border: '--border',
  text: '--text',
  textDim: '--text-dim',
  accent: '--accent',
  onAccent: '--on-accent',
  danger: '--danger',
}

function declared(id: string, token: string): string | undefined {
  return new RegExp(`${token}:\\s*(#[0-9a-fA-F]{6})`).exec(block(id))?.[1].toLowerCase()
}

describe('contrastRatio', () => {
  it('is 21 for black on white and 1 for a colour against itself', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5)
    expect(contrastRatio('#336699', '#336699')).toBeCloseTo(1, 5)
  })

  it('does not depend on which colour is passed first', () => {
    expect(contrastRatio('#0f172a', '#f1f5f9')).toBe(contrastRatio('#f1f5f9', '#0f172a'))
  })
})

describe('isThemeId', () => {
  it('accepts shipped themes and rejects anything else', () => {
    expect(THEMES.every((t) => isThemeId(t.id))).toBe(true)
    expect(isThemeId('neon')).toBe(false)
    expect(isThemeId(undefined)).toBe(false)
  })
})

describe.each(THEMES)('$label theme', ({ id, palette }) => {
  it('matches the colours declared in global.css, so the swatch previews what you get', () => {
    for (const [key, token] of Object.entries(TOKENS)) {
      const fromCss = declared(id, token)
      // Daylight and Hearth override every token; Midnight defines them all in :root.
      expect(fromCss, `${token} in ${id}`).toBe(palette[key as keyof ThemePalette])
    }
  })

  it('keeps body text at WCAG AA (4.5:1) on every surface', () => {
    for (const surface of [palette.bg, palette.bgElev, palette.bgElev2]) {
      expect(contrastRatio(palette.text, surface), `text on ${surface}`).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(palette.textDim, surface), `dim on ${surface}`).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(palette.accent, surface), `accent on ${surface}`).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('keeps text on the accent fill and danger text readable', () => {
    expect(contrastRatio(palette.onAccent, palette.accent)).toBeGreaterThanOrEqual(4.5)
    // Danger is used on --bg and --bg-elev, not on the second elevation.
    expect(contrastRatio(palette.danger, palette.bg)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(palette.danger, palette.bgElev)).toBeGreaterThanOrEqual(4.5)
  })

  it('keeps the dark chip ink readable on every colour offered to a person', () => {
    const ink = '#0b1220'
    const palettes = readFileSync(new URL('./views/settings/palette.ts', import.meta.url), 'utf8')
    const colours = palettes.match(/#[0-9a-fA-F]{6}/g) ?? []
    expect(colours.length).toBeGreaterThan(0)
    for (const c of colours) expect(contrastRatio(ink, c), c).toBeGreaterThanOrEqual(4.5)
  })
})

describe('theme borders', () => {
  it.each(THEMES.filter((t) => t.id !== 'midnight'))(
    '$label draws borders at 3:1 or better against the page',
    ({ palette }) => {
      expect(contrastRatio(palette.border, palette.bg)).toBeGreaterThanOrEqual(3)
    },
  )
})
