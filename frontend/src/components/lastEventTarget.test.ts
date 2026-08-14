import { describe, expect, it } from 'vitest'
import type { CalendarInfo } from '../api/types'
import { isStillValid, parseTarget } from './lastEventTarget'

const cal = (id: number, owner: number | null): CalendarInfo =>
  ({ id, name: `cal${id}`, claimed_by_user_id: owner }) as CalendarInfo

const CHOICES = [cal(10, 1), cal(11, 2), cal(12, null)]

describe('parseTarget', () => {
  it('reads a stored choice', () => {
    expect(parseTarget('{"profileId":1,"calendarId":10}')).toEqual({
      profileId: 1,
      calendarId: 10,
    })
  })

  it('accepts the household, whose profile really is null', () => {
    expect(parseTarget('{"profileId":null,"calendarId":12}')).toEqual({
      profileId: null,
      calendarId: 12,
    })
  })

  it('returns nothing rather than throwing on junk', () => {
    // A person can edit this, and a half-written value can be left behind. The worst
    // outcome allowed is "no memory".
    for (const raw of [
      null,
      '',
      'not json',
      '[]',
      'null',
      '{"profileId":1}',
      '{"calendarId":"ten"}',
      '{"profileId":"mike","calendarId":10}',
    ]) {
      expect(parseTarget(raw), `for ${JSON.stringify(raw)}`).toBeNull()
    }
  })
})

describe('isStillValid', () => {
  it('accepts a pair that still matches', () => {
    expect(isStillValid({ profileId: 1, calendarId: 10 }, CHOICES)).toBe(true)
    expect(isStillValid({ profileId: null, calendarId: 12 }, CHOICES)).toBe(true)
  })

  it('rejects a calendar that has been reassigned to somebody else', () => {
    // Restoring this would show Mike as the profile and file the event on a calendar
    // that is now Chrissy's.
    expect(isStillValid({ profileId: 1, calendarId: 11 }, CHOICES)).toBe(false)
  })

  it('rejects a calendar that is no longer offered', () => {
    // Syncing switched off, or the calendar deleted, since the last event.
    expect(isStillValid({ profileId: 1, calendarId: 99 }, CHOICES)).toBe(false)
    expect(isStillValid({ profileId: 1, calendarId: 10 }, [])).toBe(false)
  })

  it('rejects a calendar that has since been unclaimed', () => {
    expect(isStillValid({ profileId: 1, calendarId: 12 }, CHOICES)).toBe(false)
  })
})
