import type { CalendarEvent } from '../../api/types'

/**
 * All-day events are stored as UTC midnight boundaries and mean whole calendar dates,
 * not instants. Comparing them in local time would drag a Saturday event onto Friday for
 * anyone west of UTC, so they get compared date-to-date instead.
 */
export function overlapsDay(event: CalendarEvent, day: Date): boolean {
  if (event.all_day) {
    const key = localDateKey(day)
    return key >= utcDateKey(event.start_at) && key < utcDateKey(event.end_at)
  }
  const dayStart = startOfLocalDay(day)
  const dayEnd = new Date(dayStart)
  dayEnd.setDate(dayEnd.getDate() + 1)
  return new Date(event.start_at) < dayEnd && new Date(event.end_at) > dayStart
}

export function startOfLocalDay(day: Date): Date {
  const d = new Date(day)
  d.setHours(0, 0, 0, 0)
  return d
}

function localDateKey(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function utcDateKey(iso: string): string {
  return iso.slice(0, 10)
}
