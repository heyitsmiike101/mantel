import type { CalendarInfo, User } from '../api/types'

/** The "profile" an event is being filed under: a family member, or the household. */
export interface EventProfile {
  /** A user id, or null for calendars nobody has claimed. */
  id: number | null
  name: string
}

/** `null` is a real choice here, not a missing value: an unclaimed calendar belongs to
 *  the household rather than to a person, and it still has to be reachable. */
export const HOUSEHOLD: EventProfile = { id: null, name: 'Household' }

/** Which profiles can actually take an event?
 *
 *  Only people who own at least one usable calendar. Offering somebody with nothing to
 *  write to is a dead end: you pick their name and the calendar list underneath is
 *  empty, with nothing to say why.
 */
export function profilesWithCalendars(
  calendars: CalendarInfo[],
  users: User[],
): EventProfile[] {
  const owners = new Set(calendars.map((c) => c.claimed_by_user_id))
  const profiles: EventProfile[] = users
    .filter((u) => owners.has(u.id))
    .map((u) => ({ id: u.id, name: u.name }))

  if (owners.has(null)) profiles.push(HOUSEHOLD)
  return profiles
}

/** The calendars belonging to one profile. */
export function calendarsForProfile(
  calendars: CalendarInfo[],
  profileId: number | null,
): CalendarInfo[] {
  return calendars.filter((c) => c.claimed_by_user_id === profileId)
}

/** Which profile is an event currently filed under?
 *
 *  Derived from its calendar rather than stored, because the calendar is what actually
 *  decides whose colour an event takes -- there is no second place for this to disagree.
 */
export function profileOfCalendar(
  calendars: CalendarInfo[],
  calendarId: number | null,
): number | null {
  return calendars.find((c) => c.id === calendarId)?.claimed_by_user_id ?? null
}

/** The profile to start on, and the calendar to start on within it.
 *
 *  Prefers the profile of the calendar already chosen, so opening an existing event
 *  shows the truth. Otherwise the first profile that has somewhere to write.
 */
export function initialSelection(
  calendars: CalendarInfo[],
  users: User[],
  currentCalendarId: number | null,
): { profileId: number | null; calendarId: number | null } {
  const profiles = profilesWithCalendars(calendars, users)

  if (currentCalendarId !== null && calendars.some((c) => c.id === currentCalendarId)) {
    return {
      profileId: profileOfCalendar(calendars, currentCalendarId),
      calendarId: currentCalendarId,
    }
  }

  const first = profiles[0]
  if (!first) return { profileId: null, calendarId: null }
  return {
    profileId: first.id,
    calendarId: calendarsForProfile(calendars, first.id)[0]?.id ?? null,
  }
}
