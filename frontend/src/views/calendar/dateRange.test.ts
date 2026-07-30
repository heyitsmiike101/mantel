import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import { rangeFor, step } from './dateRange'
import { overlapsDay } from './overlap'

const at = (s: string) => new Date(s)

describe('rangeFor', () => {
  it('gives one day for today view', () => {
    const r = rangeFor('today', at('2026-07-30T15:00:00'), 0)
    expect(r.days).toHaveLength(1)
    expect(r.start.getHours()).toBe(0)
  })

  it('gives three days for 3day view', () => {
    expect(rangeFor('3day', at('2026-07-30T15:00:00'), 0).days).toHaveLength(3)
  })

  it('gives seven days starting on the configured first day', () => {
    const sunday = rangeFor('week', at('2026-07-30T15:00:00'), 0)
    expect(sunday.days).toHaveLength(7)
    expect(sunday.days[0].getDay()).toBe(0)

    const monday = rangeFor('week', at('2026-07-30T15:00:00'), 1)
    expect(monday.days[0].getDay()).toBe(1)
  })

  it('always covers a whole number of weeks in month view', () => {
    // A fractional week count silently breaks the CSS grid row template.
    for (let month = 0; month < 12; month++) {
      for (const year of [2025, 2026, 2027]) {
        for (const weekStart of [0, 1] as const) {
          const r = rangeFor('month', new Date(year, month, 15), weekStart)
          expect(r.days.length % 7, `${year}-${month + 1} weekStart=${weekStart}`).toBe(0)
          expect(r.days.length).toBeGreaterThanOrEqual(28)
          expect(r.days.length).toBeLessThanOrEqual(42)
        }
      }
    }
  })

  it('month view includes every day of the month', () => {
    const r = rangeFor('month', at('2026-02-15T12:00:00'), 0)
    const keys = r.days.map((d) => d.toDateString())
    expect(keys).toContain(new Date(2026, 1, 1).toDateString())
    expect(keys).toContain(new Date(2026, 1, 28).toDateString())
  })
})

describe('step', () => {
  it('moves by the size of the view', () => {
    const anchor = at('2026-07-30T12:00:00')
    expect(step('today', anchor, 1).getDate()).toBe(31)
    expect(step('3day', anchor, 1).getDate()).toBe(2)
    expect(step('week', anchor, -1).getDate()).toBe(23)
    expect(step('month', anchor, 1).getMonth()).toBe(7)
  })
})

describe('overlapsDay', () => {
  const event = (over: Partial<CalendarEvent>): CalendarEvent =>
    ({
      id: 1,
      all_day: false,
      start_at: '2026-07-30T21:00:00Z',
      end_at: '2026-07-30T22:00:00Z',
      ...over,
    }) as CalendarEvent

  it('matches the day a timed event falls on', () => {
    const e = event({})
    expect(overlapsDay(e, new Date(e.start_at))).toBe(true)
  })

  it('excludes an event that ends exactly at midnight', () => {
    const day = new Date(2026, 6, 31)
    const midnight = new Date(2026, 6, 31, 0, 0, 0)
    const e = event({
      start_at: new Date(2026, 6, 30, 23, 0, 0).toISOString(),
      end_at: midnight.toISOString(),
    })
    expect(overlapsDay(e, day)).toBe(false)
  })

  it('places all-day events on their calendar dates regardless of local timezone', () => {
    // Stored as UTC midnight with an exclusive end: Aug 1 and Aug 2 only.
    const e = event({
      all_day: true,
      start_at: '2026-08-01T00:00:00Z',
      end_at: '2026-08-03T00:00:00Z',
    })
    expect(overlapsDay(e, new Date(2026, 6, 31))).toBe(false)
    expect(overlapsDay(e, new Date(2026, 7, 1))).toBe(true)
    expect(overlapsDay(e, new Date(2026, 7, 2))).toBe(true)
    expect(overlapsDay(e, new Date(2026, 7, 3))).toBe(false)
  })

  it('spans every day of a multi-day timed event', () => {
    const e = event({
      start_at: new Date(2026, 7, 1, 10, 0).toISOString(),
      end_at: new Date(2026, 7, 4, 10, 0).toISOString(),
    })
    for (const d of [1, 2, 3, 4]) expect(overlapsDay(e, new Date(2026, 7, d))).toBe(true)
    expect(overlapsDay(e, new Date(2026, 7, 5))).toBe(false)
  })
})
