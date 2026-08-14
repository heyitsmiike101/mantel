import { describe, expect, it } from 'vitest'
import { endFor, toLocalInput } from './eventTimes'

describe('endFor', () => {
  it('puts the end 30 minutes after a start nobody has overridden', () => {
    expect(endFor('2026-08-14T09:00', '2026-08-14T08:00', '2026-08-14T08:30', false)).toBe(
      '2026-08-14T09:30',
    )
  })

  it('crosses midnight without inventing a date', () => {
    expect(endFor('2026-08-14T23:45', '2026-08-14T08:00', '2026-08-14T08:30', false)).toBe(
      '2026-08-15T00:15',
    )
  })

  it('keeps a length somebody chose, moving the event instead of reshaping it', () => {
    // 08:00-10:00 is two hours. Moving the start to 14:00 should give 14:00-16:00,
    // not 14:00-14:30 -- silently cutting a meeting in half is worse than no help.
    expect(endFor('2026-08-14T14:00', '2026-08-14T08:00', '2026-08-14T10:00', true)).toBe(
      '2026-08-14T16:00',
    )
  })

  it('does not carry a backwards duration along with the start', () => {
    // The end is before the start here; moving the start must not preserve that.
    expect(endFor('2026-08-14T14:00', '2026-08-14T10:00', '2026-08-14T09:00', true)).toBe(
      '2026-08-14T14:30',
    )
  })

  it('leaves the end alone while a date is half typed', () => {
    expect(endFor('2026-08-', '2026-08-14T08:00', '2026-08-14T08:30', false)).toBe(
      '2026-08-14T08:30',
    )
    expect(endFor('', '2026-08-14T08:00', '2026-08-14T08:30', true)).toBe('2026-08-14T08:30')
  })

  it('leaves the end alone if the existing values are unreadable', () => {
    expect(endFor('2026-08-14T14:00', 'nonsense', '2026-08-14T10:00', true)).toBe(
      '2026-08-14T10:00',
    )
  })
})

describe('toLocalInput', () => {
  it('pads every part, because the input silently rejects a short one', () => {
    expect(toLocalInput(new Date(2026, 0, 5, 9, 7))).toBe('2026-01-05T09:07')
  })
})
