/** "synced 5 min ago" -- the only thing that makes a last-sync timestamp readable at a
 *  glance on a wall display. Shared by the Google, Apple and Calendars tabs.
 *
 *  `now` is injectable so the tests don't depend on the wall clock. */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const mins = Math.round((now - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`
}
