import {
  addDays,
  addMonths,
  differenceInCalendarMonths,
  endOfMonth,
  endOfWeek,
  startOfDay,
  startOfMonth,
  startOfWeek,
} from 'date-fns'

export type ViewKind = 'today' | '3day' | 'week' | 'month'

export const VIEW_KINDS: ViewKind[] = ['today', '3day', 'week', 'month']

export function isViewKind(v: string | undefined): v is ViewKind {
  return !!v && (VIEW_KINDS as string[]).includes(v)
}

export interface Range {
  start: Date
  end: Date
  days: Date[]
}

/** The visible span for a view anchored on `anchor`. Month view is padded out to whole
 *  weeks so the grid is always rectangular. */
export function rangeFor(view: ViewKind, anchor: Date, weekStartsOn: 0 | 1): Range {
  if (view === 'month') {
    const start = startOfWeek(startOfMonth(anchor), { weekStartsOn })
    // endOfWeek lands on 23:59:59, so normalize before stepping to the exclusive end --
    // otherwise the grid gets 36 days and stops being a whole number of weeks.
    const end = addDays(startOfDay(endOfWeek(endOfMonth(anchor), { weekStartsOn })), 1)
    return { start, end, days: eachDay(start, end) }
  }
  if (view === 'week') {
    const start = startOfWeek(anchor, { weekStartsOn })
    return { start, end: addDays(start, 7), days: eachDay(start, addDays(start, 7)) }
  }
  const count = view === '3day' ? 3 : 1
  const start = startOfDay(anchor)
  return { start, end: addDays(start, count), days: eachDay(start, addDays(start, count)) }
}

/** How far one swipe / arrow tap moves the anchor. */
export function step(view: ViewKind, anchor: Date, direction: 1 | -1): Date {
  switch (view) {
    case 'today':
      return addDays(anchor, direction)
    case '3day':
      return addDays(anchor, 3 * direction)
    case 'week':
      return addDays(anchor, 7 * direction)
    case 'month':
      return addMonths(anchor, direction)
  }
}

/** A run of whole months, inclusive at both ends, each held as its first day. Month view
 *  renders one block per month in the window and fetches events for all of them. */
export interface MonthWindow {
  first: Date
  last: Date
}

/** How many months month view lays out either side of the one it opens on. Large, so the
 *  window rarely has to grow: growing means prepending, and correcting scrollTop while
 *  the browser is animating a wheel or fling scroll makes the view jump. Cheap because
 *  only months near the visible one render their cells (see FULL_RENDER_PAD). */
export const MONTH_INITIAL_PAD = 24

/** How many months are added when the user does scroll near an edge of the window. */
export const MONTH_EXTEND_BATCH = 12

/** Months either side of the visible one that render full grids; the rest are
 *  placeholders of the same height. Also how far events are fetched around it. */
export const FULL_RENDER_PAD = 2

export function monthWindow(
  center: Date,
  before = MONTH_INITIAL_PAD,
  after = MONTH_INITIAL_PAD,
): MonthWindow {
  const c = startOfMonth(center)
  return { first: addMonths(c, -before), last: addMonths(c, after) }
}

export function monthsIn(win: MonthWindow): Date[] {
  const n = differenceInCalendarMonths(win.last, win.first) + 1
  return Array.from({ length: n }, (_, i) => addMonths(win.first, i))
}

export function windowHas(win: MonthWindow, month: Date): boolean {
  const m = startOfMonth(month)
  return m >= win.first && m <= win.last
}

/** Grows the window by `by` months on one side. Returns the same object when `by` is 0
 *  so callers can bail out of a state update. */
export function extendWindow(win: MonthWindow, side: 'start' | 'end', by = MONTH_EXTEND_BATCH): MonthWindow {
  if (by <= 0) return win
  return side === 'start'
    ? { first: addMonths(win.first, -by), last: win.last }
    : { first: win.first, last: addMonths(win.last, by) }
}

/** The fetch range for a whole window: first grid day of the first month through the
 *  (exclusive) end of the last month's grid. Stable between renders, so the query key
 *  only changes when the window itself does. */
export function windowRange(win: MonthWindow, weekStartsOn: 0 | 1): { start: Date; end: Date } {
  return {
    start: rangeFor('month', win.first, weekStartsOn).start,
    end: rangeFor('month', win.last, weekStartsOn).end,
  }
}

function eachDay(start: Date, end: Date): Date[] {
  const out: Date[] = []
  for (let d = start; d < end; d = addDays(d, 1)) out.push(d)
  return out
}

/** What to fetch while `month` is in view: the grids of the months that render in full
 *  around it. Depends only on the visible month, so scrolling within a month never
 *  changes the query key. */
export function eventsRangeAround(month: Date, weekStartsOn: 0 | 1): { start: Date; end: Date } {
  return windowRange(monthWindow(month, FULL_RENDER_PAD, FULL_RENDER_PAD), weekStartsOn)
}
