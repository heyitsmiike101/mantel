import {
  addDays,
  addMonths,
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

function eachDay(start: Date, end: Date): Date[] {
  const out: Date[] = []
  for (let d = start; d < end; d = addDays(d, 1)) out.push(d)
  return out
}
