import { calendarLabel } from '../api/providers'
import type { CalendarInfo } from '../api/types'

/** What saving will do when an existing event's calendar was changed, or null if it
 *  stays where it is.
 *
 *  A move is a create on the new calendar plus a delete on the old one, because the
 *  providers cannot move between calendars. Saying so up front matters since the event
 *  vanishes from where it was, rather than quietly gaining a second home.
 */
export function moveNote(
  from: CalendarInfo | undefined,
  to: CalendarInfo | undefined,
): string | null {
  if (!from || !to || from.id === to.id) return null
  return `Saving moves this event to ${calendarLabel(to)}. It will be removed from ${calendarLabel(from)}.`
}
