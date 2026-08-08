import { describe, expect, it } from 'vitest'
import { providerLabel, providerPossessive } from './providers'

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
