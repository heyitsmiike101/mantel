import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../../api/types'
import { DAY_FULL_PAD, dayWindow, daysIn } from './dateRange'
import { TimeStripView } from './TimeStripView'

const event = (over: Partial<CalendarEvent>): CalendarEvent =>
  ({
    id: 1,
    calendar_id: 1,
    calendar_name: 'Family',
    color: '#3b82f6',
    user_id: null,
    title: 'Soccer practice',
    start_at: new Date(2026, 9, 15, 10, 0).toISOString(),
    end_at: new Date(2026, 9, 15, 11, 0).toISOString(),
    all_day: false,
    recurring: false,
    origin: 'local',
    sync_state: 'synced',
    editable: true,
    ...over,
  }) as CalendarEvent

// 30 days either side of Thu 15 Oct 2026: wider than the full-render pad, so the
// placeholders show up, but small enough to read.
const win = dayWindow(new Date(2026, 9, 15), 30, 30)

const render = (events: CalendarEvent[] = [], kind: 'week' | '3day' = 'week') =>
  renderToStaticMarkup(
    <TimeStripView
      kind={kind}
      window={win}
      initialStart={new Date(2026, 9, 11)}
      events={events}
      dayStartHour={8}
      dayEndHour={12}
      use24h={false}
      hourHeight={64}
      onSelectEvent={() => {}}
      onSelectSlot={() => {}}
    />,
  )

const count = (html: string, re: RegExp) => (html.match(re) ?? []).length

const allDayEvent = () =>
  event({ all_day: true, start_at: '2026-10-11T00:00:00Z', end_at: '2026-10-12T00:00:00Z' })

describe('TimeStripView', () => {
  it('lays every day of the window out as a column and a header in one strip', () => {
    const html = render()
    expect(count(html, /class="timegrid__col"/g)).toBe(daysIn(win).length)
    expect(count(html, /class="timegrid__dayhead"/g)).toBe(daysIn(win).length)
    expect(html).toContain('--n:61')
  })

  it('sizes columns for seven days in Week and three in 3 Day', () => {
    expect(render([], 'week')).toContain('--days:7')
    expect(render([], '3day')).toContain('--days:3')
  })

  it('keeps the header and all-day band in one sticky block above the hours', () => {
    const html = render([allDayEvent()])
    const top = html.indexOf('timestrip__top')
    expect(top).toBeGreaterThan(-1)
    expect(top).toBeLessThan(html.indexOf('timestrip__row--allday'))
    expect(html.indexOf('timestrip__row--allday')).toBeLessThan(html.indexOf('timestrip__row--body'))
  })

  it('shows the all-day band only when some event needs it', () => {
    expect(render()).not.toContain('timestrip__row--allday')
    expect(render([allDayEvent()])).toContain('timestrip__row--allday')
  })

  it('draws slots only in columns near the first visible day', () => {
    // Opens on 11 Oct: full columns run DAY_FULL_PAD before it to DAY_FULL_PAD after the
    // seventh visible one. The window starts 26 days before 11 Oct, so none are cut off.
    const html = render()
    const full = 2 * DAY_FULL_PAD + 7
    expect(count(html, /timegrid__slot/g)).toBe(full * 4)
    expect(count(html, /aria-hidden="true"/g)).toBe(daysIn(win).length - full)
  })

  it('keeps placeholders as tall as real columns so swapping them moves nothing', () => {
    // 4 hours at 64px.
    expect(render()).toContain('style="height:256px"')
  })

  it('draws events in nearby columns but not in placeholders', () => {
    const far = event({
      id: 2,
      title: 'Far away',
      start_at: new Date(2026, 10, 12, 10, 0).toISOString(),
      end_at: new Date(2026, 10, 12, 11, 0).toISOString(),
    })
    const html = render([event({}), far])
    expect(html).toContain('Soccer practice')
    expect(html).not.toContain('Far away')
  })

  it('keeps an empty slot and an event as separate controls', () => {
    const html = render([event({})])
    expect(html).toContain('aria-label="Add event Thu 15 8a"')
    expect(html).toMatch(/<button class="event-block"[^>]*>/)
  })

  it('puts the hour gutter in the body row, after the header block', () => {
    const html = render()
    expect(html).toContain('>8a<')
    expect(html.indexOf('timegrid__gutter"')).toBeGreaterThan(html.indexOf('timestrip__row--body'))
  })
})
