import { describe, expect, it } from 'vitest'
import { keyboardIsUp, shouldSnapBack } from './useViewportFit'

describe('shouldSnapBack', () => {
  it('snaps back when the keyboard closes and the height returns', () => {
    // iPhone 15: 812 tall, ~475 with the keyboard up.
    expect(shouldSnapBack(475, 812)).toBe(true)
  })

  it('does not snap while the keyboard is opening', () => {
    expect(shouldSnapBack(812, 475)).toBe(false)
  })

  it('ignores the small changes that are not a keyboard', () => {
    // A collapsing URL bar is worth ~60px and must not yank the page to the top
    // while somebody is reading half way down a month.
    expect(shouldSnapBack(750, 812)).toBe(false)
    expect(shouldSnapBack(812, 812)).toBe(false)
  })

  it('is a threshold, not a guess about which device', () => {
    expect(shouldSnapBack(0, 81)).toBe(true)
    expect(shouldSnapBack(0, 80)).toBe(false)
    expect(shouldSnapBack(300, 400, 150)).toBe(false)
  })
})

describe('keyboardIsUp', () => {
  it('spots a keyboard covering a third of the screen', () => {
    expect(keyboardIsUp(812, 475)).toBe(true)
  })

  it('is false when nothing is covering the window', () => {
    // The important case: with the keyboard down the hook must hand the height back
    // to CSS, so a viewport event that never arrives cannot leave the app stuck at a
    // stale pixel height with dead space under it.
    expect(keyboardIsUp(812, 812)).toBe(false)
    expect(keyboardIsUp(800, 799)).toBe(false)
  })

  it('ignores a collapsing URL bar', () => {
    expect(keyboardIsUp(812, 750)).toBe(false)
  })

  it('never reports a keyboard on a desktop window', () => {
    expect(keyboardIsUp(1080, 1080)).toBe(false)
  })
})
