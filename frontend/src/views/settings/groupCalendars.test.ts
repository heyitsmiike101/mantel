import { describe, expect, it } from 'vitest'
import type { CalendarInfo } from '../../api/types'
import { groupCalendarsBySource } from './groupCalendars'

const cal = (over: Partial<CalendarInfo> & { id: number; name: string }): CalendarInfo =>
  ({
    is_local: false,
    google_calendar_id: null,
    linked_account_id: 1,
    account_email: 'a@example.com',
    account_provider: 'google',
    claimed_by_user_id: null,
    color: '#fff',
    sync_enabled: true,
    access_role: 'owner',
    writable: true,
    last_synced_at: null,
    sync_error: null,
    ...over,
  }) as CalendarInfo

describe('groupCalendarsBySource', () => {
  it('puts each account under its own heading', () => {
    const groups = groupCalendarsBySource([
      cal({ id: 1, name: 'Work', linked_account_id: 7, account_email: 'me@work.com' }),
      cal({ id: 2, name: 'Home', linked_account_id: 8, account_email: 'me@gmail.com' }),
      cal({ id: 3, name: 'Trips', linked_account_id: 7, account_email: 'me@work.com' }),
    ])
    expect(groups.map((g) => g.label)).toEqual([
      'Google · me@gmail.com',
      'Google · me@work.com',
    ])
    expect(groups[1].calendars.map((c) => c.name)).toEqual(['Trips', 'Work'])
  })

  it('keeps two services apart even when they share an address', () => {
    // An Apple ID is usually a gmail address. Grouping on the address would put a
    // Google account and an Apple account under one heading and imply they are the
    // same thing; the account id is what actually distinguishes them.
    const groups = groupCalendarsBySource([
      cal({ id: 1, name: 'Home', linked_account_id: 1, account_provider: 'google', account_email: 'me@gmail.com' }),
      cal({ id: 2, name: 'Home', linked_account_id: 2, account_provider: 'icloud', account_email: 'me@gmail.com' }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups.map((g) => g.label)).toEqual([
      'Apple · me@gmail.com',
      'Google · me@gmail.com',
    ])
  })

  it('puts calendars made here last, next to the box that makes them', () => {
    const groups = groupCalendarsBySource([
      cal({ id: 1, name: 'Chores', is_local: true, linked_account_id: null, account_email: null, account_provider: null }),
      cal({ id: 2, name: 'Work', linked_account_id: 3, account_email: 'z@example.com' }),
    ])
    expect(groups.map((g) => g.label)).toEqual(['Google · z@example.com', 'Made here'])
    expect(groups[1].calendars.map((c) => c.name)).toEqual(['Chores'])
  })

  it('sorts calendars by name inside a group', () => {
    const groups = groupCalendarsBySource([
      cal({ id: 1, name: 'Zebra' }),
      cal({ id: 2, name: 'Apples' }),
      cal({ id: 3, name: 'Mangoes' }),
    ])
    expect(groups[0].calendars.map((c) => c.name)).toEqual(['Apples', 'Mangoes', 'Zebra'])
  })

  it('handles an empty list', () => {
    expect(groupCalendarsBySource([])).toEqual([])
  })
})
