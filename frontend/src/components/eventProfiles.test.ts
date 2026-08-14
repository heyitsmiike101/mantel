import { describe, expect, it } from 'vitest'
import type { CalendarInfo, User } from '../api/types'
import {
  calendarsForProfile,
  initialSelection,
  profileOfCalendar,
  profilesWithCalendars,
} from './eventProfiles'

const user = (id: number, name: string): User =>
  ({ id, name, color: '#fff' }) as User

const cal = (id: number, name: string, owner: number | null): CalendarInfo =>
  ({
    id,
    name,
    claimed_by_user_id: owner,
    is_local: false,
    account_email: 'a@example.com',
    account_provider: 'google',
    writable: true,
    sync_enabled: true,
  }) as CalendarInfo

const USERS = [user(1, 'Mike'), user(2, 'Chrissy'), user(3, 'Family'), user(4, 'ECLA')]
const CALS = [
  cal(10, 'Mike Google', 1),
  cal(11, 'Home', 1),
  cal(12, 'Chrissy Work', 2),
  cal(13, 'Shared', null),
]

describe('profilesWithCalendars', () => {
  it('offers only people who have somewhere to write', () => {
    // ECLA and Family own nothing usable; naming them would be a dead end -- you pick
    // the name and the calendar list below is empty with nothing to explain why.
    expect(profilesWithCalendars(CALS, USERS).map((p) => p.name)).toEqual([
      'Mike',
      'Chrissy',
      'Household',
    ])
  })

  it('adds Household only when an unclaimed calendar exists', () => {
    const claimedOnly = CALS.filter((c) => c.claimed_by_user_id !== null)
    expect(profilesWithCalendars(claimedOnly, USERS).map((p) => p.name)).toEqual([
      'Mike',
      'Chrissy',
    ])
  })

  it('is empty when there is nothing to write to at all', () => {
    expect(profilesWithCalendars([], USERS)).toEqual([])
  })
})

describe('calendarsForProfile', () => {
  it('returns only that person’s calendars', () => {
    expect(calendarsForProfile(CALS, 1).map((c) => c.name)).toEqual(['Mike Google', 'Home'])
    expect(calendarsForProfile(CALS, 2).map((c) => c.name)).toEqual(['Chrissy Work'])
  })

  it('treats Household as the unclaimed ones', () => {
    expect(calendarsForProfile(CALS, null).map((c) => c.name)).toEqual(['Shared'])
  })
})

describe('profileOfCalendar', () => {
  it('reads the owner off the calendar, which is the only record of it', () => {
    expect(profileOfCalendar(CALS, 12)).toBe(2)
    expect(profileOfCalendar(CALS, 13)).toBeNull()
    expect(profileOfCalendar(CALS, 999)).toBeNull()
  })
})

describe('initialSelection', () => {
  it('opens an existing event on its own profile, not the first one', () => {
    expect(initialSelection(CALS, USERS, 12)).toEqual({ profileId: 2, calendarId: 12 })
  })

  it('opens an event on an unclaimed calendar under Household', () => {
    expect(initialSelection(CALS, USERS, 13)).toEqual({ profileId: null, calendarId: 13 })
  })

  it('starts a new event on the first profile that has a calendar', () => {
    expect(initialSelection(CALS, USERS, null)).toEqual({ profileId: 1, calendarId: 10 })
  })

  it('ignores a calendar id that is no longer in the list', () => {
    // e.g. syncing was switched off for it since the event was made.
    expect(initialSelection(CALS, USERS, 999)).toEqual({ profileId: 1, calendarId: 10 })
  })

  it('copes with nothing to write to', () => {
    expect(initialSelection([], USERS, null)).toEqual({ profileId: null, calendarId: null })
  })
})
