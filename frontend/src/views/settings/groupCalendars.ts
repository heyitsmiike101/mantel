import { providerLabel } from '../../api/providers'
import type { CalendarInfo } from '../../api/types'

export interface CalendarGroup {
  /** Stable React key. */
  key: string
  /** "Google · you@gmail.com", or "Made here". */
  label: string
  calendars: CalendarInfo[]
}

/** Groups calendars by where they come from.
 *
 *  A household with three Google accounts and an Apple one ends up with fifteen rows
 *  that each have to repeat "Google · which@address", and the same calendar name
 *  appears under several accounts -- three "Holidays in United States", two
 *  "Mike/Chrissy Fuentes". Sorted by name they interleave, so telling them apart means
 *  reading the small print on every row. Grouped, the account is a heading and each
 *  row only has to say the things that differ.
 *
 *  Accounts come first and local calendars last, so the local group sits next to the
 *  "new local calendar" box that creates them.
 */
export function groupCalendarsBySource(calendars: CalendarInfo[]): CalendarGroup[] {
  const groups = new Map<string, CalendarGroup>()

  for (const cal of calendars) {
    // Group on the account id, not the address: an Apple ID is very often the same
    // gmail address as a linked Google account, and keying on the address would
    // collapse two separate services into one heading.
    const key = cal.is_local ? 'local' : `acct:${cal.linked_account_id}`
    const label = cal.is_local
      ? 'Made here'
      : [providerLabel(cal.account_provider), cal.account_email].filter(Boolean).join(' · ')

    const existing = groups.get(key)
    if (existing) existing.calendars.push(cal)
    else groups.set(key, { key, label, calendars: [cal] })
  }

  const ordered = [...groups.values()].sort((a, b) => {
    if (a.key === 'local') return 1
    if (b.key === 'local') return -1
    return a.label.localeCompare(b.label)
  })

  for (const group of ordered) {
    group.calendars.sort((a, b) => a.name.localeCompare(b.name))
  }
  return ordered
}
