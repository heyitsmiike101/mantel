import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import { MonthView } from './MonthView'

const days = Array.from({ length: 35 }, (_, i) => new Date(2026, 7, 1 + i - 5))

const event = (over: Partial<CalendarEvent>): CalendarEvent =>
  ({
    id: 1,
    calendar_id: 1,
    calendar_name: 'Family',
    color: '#3b82f6',
    user_id: null,
    title: 'Soccer practice',
    start_at: '2026-08-08T15:00:00Z',
    end_at: '2026-08-08T16:00:00Z',
    all_day: false,
    recurring: false,
    origin: 'local',
    sync_state: 'synced',
    editable: true,
    ...over,
  }) as CalendarEvent

const render = (events: CalendarEvent[] = []) =>
  renderToStaticMarkup(
    <MonthView
      days={days}
      anchor={new Date(2026, 7, 8)}
      events={events}
      weekStartsOn={0}
      onSelectEvent={() => {}}
      onSelectSlot={() => {}}
    />,
  )

describe('MonthView', () => {
  it('gives every day a full-cell control for adding an event', () => {
    // The bug this covers: only the date number was tappable -- about 5% of the
    // cell. On a wall-mounted touchscreen that is a target you have to aim at.
    const html = render()
    const cells = html.match(/class="month__cell"/g) ?? []
    const addLayers = html.match(/class="month__addlayer"/g) ?? []

    expect(cells.length).toBe(days.length)
    expect(addLayers.length).toBe(days.length)
  })

  it('labels each add control with its date, so it works from a keyboard', () => {
    expect(render()).toContain('aria-label="Add event on August 8"')
  })

  it('keeps the date visible without announcing it twice', () => {
    const html = render()
    // The number is decoration now; the button label already carries the date.
    expect(html).toMatch(/<span class="month__daynum" aria-hidden="true">8<\/span>/)
  })

  it('still renders events as their own controls', () => {
    // The add layer sits underneath these -- tapping a chip must open the event,
    // not start a new one.
    const html = render([event({ title: 'Soccer practice' })])
    expect(html).toContain('Soccer practice')
    expect(html).toContain('chip chip--month')
  })
})
