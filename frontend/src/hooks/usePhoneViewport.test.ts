import { describe, expect, it } from 'vitest'
import { isPhoneViewport } from './usePhoneViewport'

describe('isPhoneViewport', () => {
  it('recognises a phone held upright', () => {
    expect(isPhoneViewport(390, 844)).toBe(true) // iPhone 15
    expect(isPhoneViewport(320, 568)).toBe(true) // the smallest still in use
  })

  it('still recognises the same phone turned sideways', () => {
    // The reason this measures the short side. 844 is wider than most tablets are
    // tall, so a width test would start a slideshow on a phone in landscape.
    expect(isPhoneViewport(844, 390)).toBe(true)
    expect(isPhoneViewport(932, 430)).toBe(true) // iPhone 15 Pro Max, sideways
  })

  it('leaves tablets and wall displays alone, either way up', () => {
    expect(isPhoneViewport(820, 1180)).toBe(false) // iPad, portrait
    expect(isPhoneViewport(1180, 820)).toBe(false) // iPad, landscape
    expect(isPhoneViewport(1920, 1080)).toBe(false) // the wall
    expect(isPhoneViewport(1080, 1920)).toBe(false) // the wall, portrait
  })

  it('treats the limit as inclusive', () => {
    expect(isPhoneViewport(640, 1000)).toBe(true)
    expect(isPhoneViewport(641, 1000)).toBe(false)
  })
})
