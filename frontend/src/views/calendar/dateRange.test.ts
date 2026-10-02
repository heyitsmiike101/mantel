import { differenceInCalendarDays } from 'date-fns'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import {
  DAY_EXTEND_BATCH,
  DAY_INITIAL_PAD,
  MONTH_EXTEND_BATCH,
  MONTH_INITIAL_PAD,
  dayWindow,
  dayWindowHas,
  daysIn,
  eventsRangeAround,
  extendDayWindow,
  extendWindow,
  firstVisibleIndex,
  monthsIn,
  monthWindow,
  rangeFor,
  step,
  stripFetchRange,
  stripStartFor,
  stripStep,
  windowHas,
  windowRange,
} from './dateRange'
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

describe('month window', () => {
  it('spans the initial pad on either side of the anchor month', () => {
    const win = monthWindow(at('2026-10-17T12:00:00'))
    const months = monthsIn(win)
    expect(months).toHaveLength(2 * MONTH_INITIAL_PAD + 1)
    expect(months[0]).toEqual(new Date(2024, 9, 1))
    expect(months[MONTH_INITIAL_PAD]).toEqual(new Date(2026, 9, 1))
    expect(months[months.length - 1]).toEqual(new Date(2028, 9, 1))
  })

  it('knows whether a month is inside it, whatever day is passed', () => {
    const win = monthWindow(at('2026-10-17T12:00:00'), 3, 3)
    expect(windowHas(win, at('2026-07-31T23:00:00'))).toBe(true)
    expect(windowHas(win, at('2026-06-30T12:00:00'))).toBe(false)
    expect(windowHas(win, at('2027-02-01T00:00:00'))).toBe(false)
  })

  it('extends one side only, and not at all for zero', () => {
    const win = monthWindow(at('2026-10-17T12:00:00'), 3, 3)
    const before = extendWindow(win, 'start', 2)
    expect(before.first).toEqual(new Date(2026, 4, 1))
    expect(before.last).toEqual(win.last)
    const after = extendWindow(win, 'end', 2)
    expect(after.first).toEqual(win.first)
    expect(after.last).toEqual(new Date(2027, 2, 1))
    expect(extendWindow(win, 'end', 0)).toBe(win)
    // The default batch is what scrolling near an edge adds.
    expect(monthsIn(extendWindow(win, 'end')).length - monthsIn(win).length).toBe(MONTH_EXTEND_BATCH)
  })

  it('fetches from the first grid day of the first month to the last grid day of the last', () => {
    const win = monthWindow(at('2026-10-17T12:00:00'), 3, 3)
    const r = windowRange(win, 0)
    expect(r.start).toEqual(rangeFor('month', win.first, 0).start)
    expect(r.end).toEqual(rangeFor('month', win.last, 0).end)
    // Whole weeks, so every block's grid is covered.
    expect(differenceInCalendarDays(r.end, r.start) % 7).toBe(0)
  })
})

describe('eventsRangeAround', () => {
  it('covers two months either side of the visible one, not the whole window', () => {
    const r = eventsRangeAround(at('2026-10-17T12:00:00'), 0)
    expect(r.start).toEqual(rangeFor('month', new Date(2026, 7, 1), 0).start)
    expect(r.end).toEqual(rangeFor('month', new Date(2026, 11, 1), 0).end)
  })

  it('gives the same range for any day of the same month', () => {
    expect(eventsRangeAround(at('2026-10-01T00:00:00'), 0)).toEqual(
      eventsRangeAround(at('2026-10-31T23:00:00'), 0),
    )
  })
})

describe('day window', () => {
  it('spans the initial pad either side of the opening day', () => {
    const days = daysIn(dayWindow(at('2026-10-17T15:00:00')))
    expect(days).toHaveLength(2 * DAY_INITIAL_PAD + 1)
    expect(days[DAY_INITIAL_PAD]).toEqual(new Date(2026, 9, 17))
  })

  it('has one entry per calendar day across a daylight-saving change', () => {
    // 2026-11-01 is 25 hours long in US zones; a fixed 24h step would repeat or skip a date.
    const days = daysIn({ first: new Date(2026, 9, 30), last: new Date(2026, 10, 3) })
    expect(days.map((d) => d.getDate())).toEqual([30, 31, 1, 2, 3])
  })

  it('knows whether a day is inside it, whatever time of day is passed', () => {
    const win = dayWindow(at('2026-10-17T12:00:00'), 3, 3)
    expect(dayWindowHas(win, at('2026-10-20T23:30:00'))).toBe(true)
    expect(dayWindowHas(win, at('2026-10-21T00:00:00'))).toBe(false)
    expect(dayWindowHas(win, at('2026-10-13T23:59:00'))).toBe(false)
  })

  it('extends one side only, and not at all for zero', () => {
    const win = dayWindow(at('2026-10-17T12:00:00'), 3, 3)
    expect(extendDayWindow(win, 'start', 2).first).toEqual(new Date(2026, 9, 12))
    expect(extendDayWindow(win, 'start', 2).last).toEqual(win.last)
    expect(extendDayWindow(win, 'end', 2).last).toEqual(new Date(2026, 9, 22))
    expect(extendDayWindow(win, 'end', 0)).toBe(win)
  })

  it('grows by whole weeks, so its edges stay on the same weekday', () => {
    expect(DAY_EXTEND_BATCH % 7).toBe(0)
  })
})

describe('strip navigation', () => {
  // Thursday 15 Oct 2026.
  const thu = new Date(2026, 9, 15, 14, 30)

  it('opens Week on the week start for either first weekday', () => {
    expect(stripStartFor('week', thu, 0)).toEqual(new Date(2026, 9, 11))
    expect(stripStartFor('week', thu, 1)).toEqual(new Date(2026, 9, 12))
  })

  it('opens 3 Day on the day itself, at midnight', () => {
    expect(stripStartFor('3day', thu, 0)).toEqual(new Date(2026, 9, 15))
  })

  it('steps Week by seven days from a week start', () => {
    const sun = new Date(2026, 9, 11)
    expect(stripStep('week', sun, 1, 0)).toEqual(new Date(2026, 9, 18))
    expect(stripStep('week', sun, -1, 0)).toEqual(new Date(2026, 9, 4))
  })

  it('lands Week on a week start even when the view was left mid-week', () => {
    // Otherwise a scroll that stopped on a Thursday would make the arrows walk
    // Thursday to Thursday and never show a whole week again.
    for (const weekStart of [0, 1] as const) {
      for (const dir of [1, -1] as const) {
        expect(stripStep('week', thu, dir, weekStart).getDay()).toBe(weekStart)
      }
    }
    expect(stripStep('week', thu, 1, 0)).toEqual(new Date(2026, 9, 18))
    expect(stripStep('week', thu, -1, 0)).toEqual(new Date(2026, 9, 4))
  })

  it('steps 3 Day by exactly three days', () => {
    expect(stripStep('3day', new Date(2026, 9, 15), 1, 0)).toEqual(new Date(2026, 9, 18))
    expect(stripStep('3day', new Date(2026, 9, 15), -1, 0)).toEqual(new Date(2026, 9, 12))
  })
})

describe('firstVisibleIndex', () => {
  it('is the column whose left edge is at or past the scroll position', () => {
    expect(firstVisibleIndex(0, 100)).toBe(0)
    expect(firstVisibleIndex(300, 100)).toBe(3)
    expect(firstVisibleIndex(301.5, 100)).toBe(4)
  })

  it('forgives a snap that landed a pixel short', () => {
    expect(firstVisibleIndex(299.4, 100)).toBe(3)
  })

  it('never goes negative or divides by zero', () => {
    expect(firstVisibleIndex(-50, 100)).toBe(0)
    expect(firstVisibleIndex(500, 0)).toBe(0)
  })
})

describe('stripFetchRange', () => {
  it('covers the visible days plus a span either side, wherever in its bucket the view is', () => {
    for (const span of [3, 7]) {
      for (let offset = 0; offset < 40; offset++) {
        const start = new Date(2026, 9, 1 + offset)
        const r = stripFetchRange(start, span)
        expect(r.start <= new Date(2026, 9, 1 + offset - span), `span ${span} +${offset} start`).toBe(true)
        expect(r.end >= new Date(2026, 9, 1 + offset + 2 * span), `span ${span} +${offset} end`).toBe(true)
      }
    }
  })

  it('keeps the same range (so the same query) while the view stays in one bucket', () => {
    expect(stripFetchRange(new Date(2026, 9, 14), 7)).toEqual(stripFetchRange(new Date(2026, 9, 14, 18), 7))
    const starts = new Set<number>()
    for (let d = 0; d < 7; d++) starts.add(stripFetchRange(new Date(2026, 9, 12 + d), 7).start.getTime())
    // Seven consecutive first-days can touch two buckets, never more.
    expect(starts.size).toBeLessThanOrEqual(2)
  })
})
