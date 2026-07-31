import { describe, expect, it } from 'vitest'
import { isPersonVisible, parseHidden, toggleId } from './usePersonFilter'

describe('parseHidden', () => {
  it('treats an empty store as everyone visible', () => {
    expect(parseHidden(null)).toEqual([])
    expect(parseHidden('[]')).toEqual([])
  })

  it('restores a previous choice', () => {
    expect(parseHidden('[3,4]')).toEqual([3, 4])
  })

  it('survives corrupt or hostile stored data', () => {
    expect(parseHidden('not json')).toEqual([])
    expect(parseHidden('{"a":1}')).toEqual([])
    expect(parseHidden('[1,"two",null,3]')).toEqual([1, 3])
  })
})

describe('toggleId', () => {
  it('hides a visible person and shows a hidden one', () => {
    expect(toggleId([], 2)).toEqual([2])
    expect(toggleId([2], 2)).toEqual([])
  })

  it('leaves the others alone', () => {
    expect(toggleId([1, 3], 2)).toEqual([1, 3, 2])
    expect(toggleId([1, 2, 3], 2)).toEqual([1, 3])
  })
})

describe('isPersonVisible', () => {
  it('shows everyone when nothing is hidden', () => {
    expect(isPersonVisible([], 1)).toBe(true)
    expect(isPersonVisible([], 99)).toBe(true)
  })

  it('hides exactly the toggled-off people', () => {
    expect(isPersonVisible([2], 1)).toBe(true)
    expect(isPersonVisible([2], 2)).toBe(false)
  })

  it('shows a family member added after the filter was set', () => {
    // This is why hidden ids are stored rather than visible ones: a person added
    // to the family later must not arrive invisible.
    expect(isPersonVisible([1, 2], 3)).toBe(true)
  })

  it('keeps unowned events visible even when everybody is hidden', () => {
    // The shared "Family" calendar starts unclaimed; hiding every person must
    // not empty the calendar.
    expect(isPersonVisible([1, 2, 3], null)).toBe(true)
    expect(isPersonVisible([1, 2, 3], undefined)).toBe(true)
  })
})
