import { describe, expect, it } from 'vitest'
import type { CalendarInfo } from '../api/types'
import { pickableCalendars } from './pickableCalendars'

const cal = (over: Partial<CalendarInfo> & { id: number; name: string }): CalendarInfo =>
  ({
    is_local: false,
    google_calendar_id: null,
    linked_account_id: 1,
    account_email: 'a@example.com',
    claimed_by_user_id: null,
    color: '#fff',
    sync_enabled: true,
    access_role: 'owner',
    writable: true,
    last_synced_at: null,
    sync_error: null,
    ...over,
  }) as CalendarInfo

describe('pickableCalendars', () => {
  it('offers a syncing, writable Google calendar', () => {
    const list = [cal({ id: 1, name: 'Family' })]
    expect(pickableCalendars(list).map((c) => c.name)).toEqual(['Family'])
  })

  it('hides a Google calendar that is switched off — the push queue would drop the event', () => {
    const list = [cal({ id: 1, name: 'Off', sync_enabled: false })]
    expect(pickableCalendars(list)).toEqual([])
  })

  it('hides a read-only Google calendar', () => {
    const list = [cal({ id: 1, name: 'Holidays', writable: false })]
    expect(pickableCalendars(list)).toEqual([])
  })

  it('keeps local calendars even though sync_enabled is false for all of them', () => {
    // The regression this file exists for. POST /api/calendars creates local
    // calendars with sync_enabled=false deliberately, so testing them the same way
    // as Google calendars empties the picker on a fresh install -- including the
    // "Family" calendar bootstrap creates, which is the only one there is.
    const list = [
      cal({ id: 1, name: 'Family', is_local: true, sync_enabled: false, linked_account_id: null }),
      cal({ id: 2, name: 'Chores', is_local: true, sync_enabled: false, linked_account_id: null }),
    ]
    expect(pickableCalendars(list).map((c) => c.name)).toEqual(['Family', 'Chores'])
  })

  it("keeps the event's own calendar when editing, even if it is now switched off", () => {
    const list = [
      cal({ id: 1, name: 'On' }),
      cal({ id: 2, name: 'Since switched off', sync_enabled: false }),
    ]
    expect(pickableCalendars(list, 2).map((c) => c.name)).toEqual(['On', 'Since switched off'])
    expect(pickableCalendars(list, null).map((c) => c.name)).toEqual(['On'])
  })

  it('matches the live instance: 5 of 12 calendars are pickable', () => {
    // Straight from GET /api/calendars on the running install, which is the data
    // that showed local calendars carry sync_enabled=false.
    const live = [
      cal({ id: 1, name: 'Brightwheel Christine Ford', writable: false }),
      cal({ id: 2, name: 'Brightwheel Michael Fuentes', writable: false, sync_enabled: false }),
      cal({ id: 3, name: 'Chrissy Work', is_local: true, sync_enabled: false }),
      cal({ id: 4, name: 'Family (local)', is_local: true, sync_enabled: false }),
      cal({ id: 5, name: 'Family (google)', sync_enabled: false }),
      cal({ id: 6, name: 'Follow Up Boss', sync_enabled: false }),
      cal({ id: 7, name: 'Holidays', writable: false, sync_enabled: false }),
      cal({ id: 8, name: 'Mike/Chrissy Fuentes', sync_enabled: true }),
      cal({ id: 9, name: 'Mike/Chrissy Fuentes (dup)', sync_enabled: false }),
      cal({ id: 10, name: 'chrissyaford@gmail.com', sync_enabled: false }),
      cal({ id: 11, name: 'mfuentes@realestatefuentes.com', sync_enabled: true }),
      cal({ id: 12, name: 'mikevfuentes@gmail.com', sync_enabled: true }),
    ]
    expect(pickableCalendars(live).map((c) => c.name)).toEqual([
      'Chrissy Work',
      'Family (local)',
      'Mike/Chrissy Fuentes',
      'mfuentes@realestatefuentes.com',
      'mikevfuentes@gmail.com',
    ])
  })
})
