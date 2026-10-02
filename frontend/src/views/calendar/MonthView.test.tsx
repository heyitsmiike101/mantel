import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import { MonthView } from './MonthView'
import { FULL_RENDER_PAD, monthsIn, monthWindow, rangeFor } from './dateRange'

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

// October 2026 +/- one month. Small on purpose: the structure is what is under test.
const win = monthWindow(new Date(2026, 9, 15), 1, 1)

const render = (events: CalendarEvent[] = []) =>
  renderToStaticMarkup(
    <MonthView
      window={win}
      initialMonth={new Date(2026, 9, 1)}
      events={events}
      weekStartsOn={0}
      onSelectEvent={() => {}}
      onSelectSlot={() => {}}
    />,
  )

const blockFor = (html: string, key: string) => {
  const start = html.indexOf(`data-month="${key}"`)
  const next = html.indexOf('data-month="', start + 1)
  return html.slice(start, next === -1 ? undefined : next)
}

const cellCount = (months: Date[]) =>
  months.reduce((n, m) => n + rangeFor('month', m, 0).days.length, 0)

describe('MonthView', () => {
  it('renders one block per month in the window, in order', () => {
    const html = render()
    const keys = [...html.matchAll(/<section class="month" data-month="([\d-]+)"/g)].map((m) => m[1])
    expect(keys).toEqual(['2026-09', '2026-10', '2026-11'])
  })

  it('labels each block with its month', () => {
    const html = render()
    expect(html).toContain('>September 2026<')
    expect(html).toContain('>October 2026<')
    expect(html).toContain('>November 2026<')
  })

  it('gives every day in every block a full-cell control for adding an event', () => {
    // The bug this covers: only the date number was tappable -- about 5% of the
    // cell. On a wall-mounted touchscreen that is a target you have to aim at.
    const html = render()
    const cells = html.match(/class="month__cell"/g) ?? []
    const addLayers = html.match(/class="month__addlayer"/g) ?? []
    const expected = cellCount(monthsIn(win))

    expect(cells.length).toBe(expected)
    expect(addLayers.length).toBe(expected)
  })

  it('labels each add control with its date, so it works from a keyboard', () => {
    expect(blockFor(render(), '2026-10')).toContain('aria-label="Add event on October 8"')
  })

  it('keeps the date visible without announcing it twice', () => {
    // The number is decoration now; the button label already carries the date.
    expect(render()).toMatch(/<span class="month__daynum" aria-hidden="true">8<\/span>/)
  })

  it('dims the days that belong to the neighbouring month, per block', () => {
    // October 2026 starts on a Thursday and ends on a Saturday: its 5-week grid opens
    // with 4 September days and has no trailing November ones (Sunday start).
    const oct = blockFor(render(), '2026-10')
    const outside = oct.match(/data-outside="true"/g) ?? []
    const inside = oct.match(/data-outside="false"/g) ?? []
    expect(inside.length).toBe(31)
    expect(outside.length).toBe(35 - 31)
  })

  it('places an event in the block for its month, not every block', () => {
    const html = render([event({ title: 'Soccer practice', start_at: '2026-11-12T15:00:00Z', end_at: '2026-11-12T16:00:00Z' })])
    expect(blockFor(html, '2026-11')).toContain('Soccer practice')
    expect(blockFor(html, '2026-09')).not.toContain('Soccer practice')
    expect(blockFor(html, '2026-10')).not.toContain('Soccer practice')
  })

  it('shows an event on a day that sits in two grids in both blocks', () => {
    // 28 Sep is a day of September and also a (dimmed) leading cell of October's grid.
    const html = render([event({ title: 'Dentist', start_at: '2026-09-28T18:00:00Z', end_at: '2026-09-28T19:00:00Z' })])
    expect(blockFor(html, '2026-09')).toContain('Dentist')
    expect(blockFor(html, '2026-10')).toContain('Dentist')
    expect(blockFor(html, '2026-11')).not.toContain('Dentist')
  })

  it('still renders events as their own controls', () => {
    // The add layer sits underneath these -- tapping a chip must open the event,
    // not start a new one.
    const html = render([event({ title: 'Soccer practice', start_at: '2026-10-08T15:00:00Z', end_at: '2026-10-08T16:00:00Z' })])
    expect(html).toContain('Soccer practice')
    expect(html).toContain('chip chip--month')
  })

  it('caps a crowded day at four chips and counts the rest', () => {
    const many = Array.from({ length: 6 }, (_, i) =>
      event({ id: i + 1, title: `E${i}`, start_at: '2026-10-08T15:00:00Z', end_at: '2026-10-08T16:00:00Z' }),
    )
    expect(blockFor(render(many), '2026-10')).toContain('+2 more')
  })

  describe('far from the month in view', () => {
    const wide = monthWindow(new Date(2026, 9, 15), 6, 6)
    const renderWide = (events: CalendarEvent[] = []) =>
      renderToStaticMarkup(
        <MonthView
          window={wide}
          initialMonth={new Date(2026, 9, 1)}
          events={events}
          weekStartsOn={0}
          onSelectEvent={() => {}}
          onSelectSlot={() => {}}
        />,
      )

    it('renders a block for every month but full grids only near the visible one', () => {
      const html = renderWide()
      expect(html.match(/data-month="/g)).toHaveLength(13)
      expect(html.match(/month--placeholder/g)).toHaveLength(13 - (2 * FULL_RENDER_PAD + 1))
      expect(blockFor(html, '2026-10')).toContain('month__cell')
      expect(blockFor(html, '2026-08')).toContain('month__cell')
      expect(blockFor(html, '2026-12')).toContain('month__cell')
    })

    it('keeps a placeholder to its label: no cells, hidden from screen readers', () => {
      const far = blockFor(renderWide(), '2026-04')
      expect(far).toContain('month--placeholder')
      expect(far).toContain('aria-hidden')
      expect(far).toContain('>April 2026<')
      expect(far).not.toContain('month__cell')
      expect(far).not.toContain('month__addlayer')
    })

    it('does not draw events in placeholders', () => {
      const html = renderWide([
        event({ title: 'Far away', start_at: '2026-04-08T15:00:00Z', end_at: '2026-04-08T16:00:00Z' }),
      ])
      expect(html).not.toContain('Far away')
    })
  })
})
