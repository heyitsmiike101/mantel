import { describe, expect, it } from 'vitest'
import { dockerUpgradeHint, hasUpdate, safeReleaseUrl, versionBadgeLabel } from './updateNotice'

describe('versionBadgeLabel', () => {
  it('shows just the version when nothing newer exists', () => {
    expect(versionBadgeLabel('0.5.9', false)).toBe('v0.5.9')
  })

  it('adds "Update available" when a newer release exists', () => {
    expect(versionBadgeLabel('0.5.9', true)).toBe('v0.5.9 · Update available')
  })
})

describe('hasUpdate', () => {
  it('needs both the flag and a version to name', () => {
    expect(hasUpdate({ version: '0.5.9', update_available: true, latest_version: '0.5.10' })).toBe(
      true,
    )
    expect(hasUpdate({ version: '0.5.9', update_available: true, latest_version: null })).toBe(
      false,
    )
    expect(hasUpdate({ version: '0.5.9' })).toBe(false) // an older server without the fields
  })
})

describe('safeReleaseUrl', () => {
  it('accepts a GitHub https link and nothing else', () => {
    expect(safeReleaseUrl('https://github.com/heyitsmiike101/mantel/compare/v0.5.9...v0.5.10')).toContain(
      'github.com',
    )
    expect(safeReleaseUrl('javascript:alert(1)')).toBeNull()
    expect(safeReleaseUrl('https://evil.example/github.com')).toBeNull()
    expect(safeReleaseUrl(null)).toBeNull()
  })
})

describe('dockerUpgradeHint', () => {
  it('names the image tag to pull', () => {
    expect(dockerUpgradeHint('0.5.10')).toContain('ghcr.io/heyitsmiike101/mantel:0.5.10')
  })
})
