import { describe, expect, it } from 'vitest'
import { isWithinSleepWindow } from './useIdle'

const at = (hour: number, minute = 0) => new Date(2026, 6, 30, hour, minute)

describe('isWithinSleepWindow', () => {
  it('handles a window that crosses midnight', () => {
    // 23:00 -> 07:00 is the normal case and the one a naive comparison gets wrong.
    expect(isWithinSleepWindow(23, 7, at(23, 30))).toBe(true)
    expect(isWithinSleepWindow(23, 7, at(2))).toBe(true)
    expect(isWithinSleepWindow(23, 7, at(6, 59))).toBe(true)
    expect(isWithinSleepWindow(23, 7, at(7))).toBe(false)
    expect(isWithinSleepWindow(23, 7, at(12))).toBe(false)
    expect(isWithinSleepWindow(23, 7, at(22, 59))).toBe(false)
  })

  it('handles a same-day window', () => {
    expect(isWithinSleepWindow(1, 6, at(3))).toBe(true)
    expect(isWithinSleepWindow(1, 6, at(0, 30))).toBe(false)
    expect(isWithinSleepWindow(1, 6, at(6))).toBe(false)
  })

  it('is never asleep when start and end match', () => {
    for (const hour of [0, 6, 12, 23]) {
      expect(isWithinSleepWindow(9, 9, at(hour))).toBe(false)
    }
  })

  it('is inclusive of the start minute and exclusive of the end', () => {
    expect(isWithinSleepWindow(22, 8, at(22, 0))).toBe(true)
    expect(isWithinSleepWindow(22, 8, at(8, 0))).toBe(false)
  })
})
