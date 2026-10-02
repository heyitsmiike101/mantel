import {
  addDays,
  addMonths,
  differenceInCalendarDays,
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

/** Week and 3 Day are one continuous strip of day columns rather than pages. */
export type StripKind = '3day' | 'week'

export function isStripKind(k: ViewKind | null): k is StripKind {
  return k === '3day' || k === 'week'
}

/** Day columns a strip shows at once. */
export function spanOf(kind: StripKind): number {
  return kind === 'week' ? 7 : 3
}

/** A run of whole days, inclusive at both ends, each held as local midnight. */
export interface DayWindow {
  first: Date
  last: Date
}

/** Days laid out either side of the one the strip opens on. Large so the window rarely has
 *  to grow (growing means prepending, which has to correct scrollLeft); cheap because only
 *  columns near the view render their hour slots. */
export const DAY_INITIAL_PAD = 26 * 7

/** Days added when the user does scroll near an edge. A whole number of weeks, so the
 *  window's edges stay on the same weekday. */
export const DAY_EXTEND_BATCH = 13 * 7

/** Columns either side of the visible ones that render in full; the rest are placeholders
 *  of the same size. Two spans covers a fast flick between two paints. */
export const DAY_FULL_PAD = 14

export function dayWindow(center: Date, before = DAY_INITIAL_PAD, after = DAY_INITIAL_PAD): DayWindow {
  const c = startOfDay(center)
  return { first: addDays(c, -before), last: addDays(c, after) }
}

export function daysIn(win: DayWindow): Date[] {
  const n = differenceInCalendarDays(win.last, win.first) + 1
  return Array.from({ length: n }, (_, i) => addDays(win.first, i))
}

export function dayWindowHas(win: DayWindow, day: Date): boolean {
  const d = startOfDay(day)
  return d >= win.first && d <= win.last
}

/** Grows the window by `by` days on one side. Same object back for 0, so callers can bail
 *  out of a state update. */
export function extendDayWindow(win: DayWindow, side: 'start' | 'end', by = DAY_EXTEND_BATCH): DayWindow {
  if (by <= 0) return win
  return side === 'start'
    ? { first: addDays(win.first, -by), last: win.last }
    : { first: win.first, last: addDays(win.last, by) }
}

/** The day a strip should have in its first column to show `day` the way the view means
 *  it: the whole week containing it for Week, the day itself for 3 Day. */
export function stripStartFor(kind: StripKind, day: Date, weekStartsOn: 0 | 1): Date {
  return kind === 'week' ? startOfWeek(day, { weekStartsOn }) : startOfDay(day)
}

/** Where the arrows go from the first visible day. Week lands on a week start however far
 *  into a week the view was left, so repeated taps stay aligned; 3 Day just moves three
 *  days. */
export function stripStep(kind: StripKind, from: Date, direction: 1 | -1, weekStartsOn: 0 | 1): Date {
  const moved = addDays(from, spanOf(kind) * direction)
  return stripStartFor(kind, moved, weekStartsOn)
}

/** The first fully visible column for a horizontal scroll position. One pixel of slack,
 *  because a snapped scroll can land a fraction short of the boundary. */
export function firstVisibleIndex(scrollLeft: number, colWidth: number): number {
  if (colWidth <= 0) return 0
  return Math.max(0, Math.ceil((scrollLeft - 1) / colWidth))
}

/** What to fetch while the strip's first visible day is `start`. Bucketed by span, so the
 *  query key changes once per span scrolled rather than per column; always covers the
 *  visible days plus at least one span either side, which is what keeps events in place
 *  while the next range loads. */
export function stripFetchRange(start: Date, span: number): { start: Date; end: Date } {
  const bucket = Math.floor(differenceInCalendarDays(start, STRIP_EPOCH) / span)
  const from = addDays(STRIP_EPOCH, (bucket - 1) * span)
  return { start: from, end: addDays(from, 4 * span) }
}

const STRIP_EPOCH = new Date(2000, 0, 1)
