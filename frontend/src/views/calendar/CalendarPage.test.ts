import { describe, expect, it } from 'vitest'
import { dateFromQuery } from './CalendarPage'

describe('calendar URL date', () => {
  it('creates a local date without shifting the selected day', () => {
    const date = dateFromQuery('2026-10-15')
    expect(date).toEqual(new Date(2026, 9, 15))
    expect(date?.getHours()).toBe(0)
  })

  it('ignores missing and invalid dates', () => {
    expect(dateFromQuery(null)).toBeNull()
    expect(dateFromQuery('2026-02-30')).toBeNull()
    expect(dateFromQuery('2026-10-15T00:00:00Z')).toBeNull()
    expect(dateFromQuery('2024-02-29')).toEqual(new Date(2024, 1, 29))
  })
})
