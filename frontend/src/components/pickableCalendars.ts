import type { CalendarInfo } from '../api/types'

/** Which calendars may an event be put on?
 *
 *  Two rules, and the second one is the point of this file:
 *
 *  - It has to be writable. A calendar Google says we can only read can't take events.
 *  - A *Google* calendar has to be syncing. `push_pending` skips calendars with
 *    sync_enabled off, so an event created on one would save here, appear on the wall,
 *    and never reach Google — silently. Better not to offer it.
 *
 *  Local calendars are exempt from the second rule: `POST /api/calendars` creates them
 *  with `sync_enabled = false` on purpose, because there is nothing to sync them with.
 *  Testing them the same way would hide every local calendar — including the "Family"
 *  one created on first run — leaving a fresh install with nothing to add events to and
 *  no toggle anywhere to fix it, since the Syncing switch is only shown for Google
 *  calendars.
 *
 *  `currentId` keeps the calendar an event already lives on in the list even when it
 *  fails these rules, so opening an old event doesn't silently relocate it.
 */
export function pickableCalendars(
  calendars: CalendarInfo[],
  currentId?: number | null,
): CalendarInfo[] {
  return calendars.filter(
    (c) =>
      (c.writable && (c.is_local || c.sync_enabled)) ||
      (currentId !== null && currentId !== undefined && c.id === currentId),
  )
}
