import { describe, expect, it } from 'vitest'
import type { CalendarInfo } from '../api/types'
import { moveNote } from './moveNote'

const cal = (over: Partial<CalendarInfo> & { id: number; name: string }): CalendarInfo =>
  ({
    is_local: true,
    account_email: null,
    account_provider: null,
    ...over,
  }) as CalendarInfo

describe('moveNote', () => {
  it('says nothing while the event stays on its calendar', () => {
    const home = cal({ id: 1, name: 'Home' })
    expect(moveNote(home, home)).toBeNull()
  })

  it('names both calendars when the event is moving', () => {
    const note = moveNote(cal({ id: 1, name: 'Home' }), cal({ id: 2, name: 'Chores' }))
    expect(note).toBe('Saving moves this event to Chores. It will be removed from Home.')
  })

  it('says nothing before the calendars have loaded', () => {
    expect(moveNote(undefined, cal({ id: 2, name: 'Chores' }))).toBeNull()
  })
})
