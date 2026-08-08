import { describe, expect, it } from 'vitest'
import { calendarLabel, providerLabel, providerPossessive } from './providers'

describe('providerLabel', () => {
  it('calls iCloud "Apple", which is what the person sees on their phone', () => {
    expect(providerLabel('icloud')).toBe('Apple')
  })

  it('labels Google', () => {
    expect(providerLabel('google')).toBe('Google')
  })

  it('falls back for a local calendar or an unknown provider', () => {
    expect(providerLabel(null)).toBe('Synced')
    expect(providerLabel(undefined)).toBe('Synced')
    expect(providerLabel('fastmail')).toBe('Synced')
  })
})

describe('providerPossessive', () => {
  it('names where to go and change it', () => {
    expect(providerPossessive('icloud')).toBe('Apple Calendar')
    expect(providerPossessive('google')).toBe('Google')
  })

  it("doesn't invent a service name it doesn't know", () => {
    expect(providerPossessive(null)).toBe('the service it came from')
  })
})

describe('calendarLabel', () => {
  it('tells apart two accounts that share an address', () => {
    // The bug this exists for: an Apple ID is very often a gmail address, so both
    // rows read "Family (mikevfuentes@gmail.com)" and the picker was a coin flip.
    const google = { name: 'Family', account_provider: 'google', account_email: 'me@gmail.com' }
    const apple = { name: 'Family', account_provider: 'icloud', account_email: 'me@gmail.com' }

    expect(calendarLabel(google)).toBe('Family (Google · me@gmail.com)')
    expect(calendarLabel(apple)).toBe('Family (Apple · me@gmail.com)')
    expect(calendarLabel(google)).not.toBe(calendarLabel(apple))
  })

  it('leaves a local calendar unadorned', () => {
    expect(calendarLabel({ name: 'Chores' })).toBe('Chores')
    expect(calendarLabel({ name: 'Chores', account_provider: null, account_email: null })).toBe(
      'Chores',
    )
  })

  it('still names the service when the address is missing', () => {
    expect(calendarLabel({ name: 'Holidays', account_provider: 'icloud' })).toBe(
      'Holidays (Apple)',
    )
  })
})
