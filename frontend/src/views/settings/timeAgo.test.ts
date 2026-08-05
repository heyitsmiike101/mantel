import { describe, expect, it } from 'vitest'
import { timeAgo } from './timeAgo'

const NOW = Date.parse('2026-08-01T12:00:00Z')
const ago = (ms: number) => new Date(NOW - ms).toISOString()

const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

describe('timeAgo', () => {
  it('says "just now" under a minute', () => {
    expect(timeAgo(ago(0), NOW)).toBe('just now')
    expect(timeAgo(ago(20 * SECOND), NOW)).toBe('just now')
  })

  it('counts minutes, then hours, then days', () => {
    expect(timeAgo(ago(5 * MINUTE), NOW)).toBe('5 min ago')
    expect(timeAgo(ago(59 * MINUTE), NOW)).toBe('59 min ago')
    expect(timeAgo(ago(3 * HOUR), NOW)).toBe('3h ago')
    expect(timeAgo(ago(3 * DAY), NOW)).toBe('3d ago')
  })

  it("doesn't report a future timestamp as a huge age", () => {
    // Clock skew between the server and a wall tablet is real; this should read
    // as "just now" rather than "-3 min ago".
    expect(timeAgo(ago(-30 * SECOND), NOW)).toBe('just now')
  })
})
