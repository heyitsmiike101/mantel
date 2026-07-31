import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import { layout } from './TimeGridView'

/** hourHeight as CalendarPage computes it: 64px * the --scale of the display setting. */
const HOUR = { normal: 64, large: 64 * 1.2, wall: 64 * 1.45 }

/** --font-xs is 0.75rem * scale at line-height 1.2, and .event-block adds 3px of padding
 *  top and bottom. This is what one and two rendered lines of chip text actually cost. */
const lineHeight = (scale: number) => 12 * scale * 1.2
const textHeight = (lines: number, scale: number) => lines * lineHeight(scale) + 6

const day = new Date('2026-07-30T00:00:00')

function event(startAt: string, minutes: number): CalendarEvent {
  const start = new Date(startAt)
  return {
    id: 1,
    calendar_id: 1,
    calendar_name: 'Home',
    color: '#38bdf8',
    user_id: null,
    title: 'Standup',
    description: null,
    location: null,
    start_at: start.toISOString(),
    end_at: new Date(start.getTime() + minutes * 60_000).toISOString(),
    all_day: false,
    timezone: null,
    recurring: false,
    recurrence_rule: null,
    recurrence_text: null,
    origin: 'local',
    sync_state: 'clean',
    editable: true,
  }
}

const place = (minutes: number, hourHeight: number) =>
  layout([event('2026-07-30T08:45:00', minutes)], day, hourHeight)[0]

describe('layout', () => {
  it.each([
    ['normal', HOUR.normal, 1],
    ['large', HOUR.large, 1.2],
    ['wall', HOUR.wall, 1.45],
  ])('collapses short events to one line at %s scale', (_name, hourHeight, scale) => {
    // 15 and 30 minute blocks cannot fit a stacked title + time at any scale, so they get
    // the single-line treatment -- and are still tall enough for that one line.
    for (const minutes of [15, 30]) {
      const block = place(minutes, hourHeight)
      expect(block.compact).toBe(true)
      expect(block.height).toBeGreaterThanOrEqual(textHeight(1, scale))
    }

    // An hour has room for both lines, so it keeps the stacked layout.
    const hourLong = place(60, hourHeight)
    expect(hourLong.compact).toBe(false)
    expect(hourLong.height).toBeGreaterThanOrEqual(textHeight(2, scale))
  })

  it.each([
    ['normal', HOUR.normal, 1],
    ['large', HOUR.large, 1.2],
    ['wall', HOUR.wall, 1.45],
  ])('only stacks two lines when they fit at %s scale', (_name, hourHeight, scale) => {
    // Whatever the cutoff is, a block on the tall side of it must have the room.
    for (let minutes = 5; minutes <= 120; minutes += 5) {
      const block = place(minutes, hourHeight)
      if (!block.compact) expect(block.height).toBeGreaterThanOrEqual(textHeight(2, scale))
    }
  })

  it('keeps a minimum height so a one-line chip is never clipped', () => {
    // A 5-minute event is 8px of grid at the normal scale; it still has to be readable.
    expect(place(5, HOUR.normal).height).toBeGreaterThanOrEqual(textHeight(1, 1))
    expect(place(5, HOUR.wall).height).toBeGreaterThanOrEqual(textHeight(1, 1.45))
  })

  it('positions and sizes long events from the grid, not the minimum', () => {
    const block = place(120, HOUR.normal)
    expect(block.top).toBeCloseTo(8.75 * HOUR.normal)
    expect(block.height).toBeCloseTo(2 * HOUR.normal - 2)
  })

  it('splits overlapping events into side-by-side columns', () => {
    const a = { ...event('2026-07-30T09:00:00', 60), id: 1 }
    const b = { ...event('2026-07-30T09:30:00', 60), id: 2 }
    const placed = layout([a, b], day, HOUR.normal)
    expect(placed.map((p) => p.left)).toEqual([0, 50])
  })
})
