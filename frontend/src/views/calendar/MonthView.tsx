import { addDays, differenceInCalendarMonths, format, isSameMonth, isToday } from 'date-fns'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CalendarEvent } from '../../api/types'
import { useLightSnap } from '../../hooks/useLightSnap'
import { FULL_RENDER_PAD, monthsIn, rangeFor, type MonthWindow } from './dateRange'
import { overlapsDay } from './overlap'

/** Ask the scroller to bring a month to the top. `id` makes repeat requests for the same
 *  month (tapping Today twice) distinct. */
export interface MonthScrollRequest {
  month: Date
  id: number
}

interface Props {
  window: MonthWindow
  /** The month to open on. Read once, on mount; after that the user (or a scroll
   *  request) owns the scroll position. */
  initialMonth: Date
  events: CalendarEvent[]
  weekStartsOn: 0 | 1
  scrollRequest?: MonthScrollRequest | null
  onVisibleMonthChange?: (month: Date) => void
  /** The user scrolled close to one end of the window; the parent should add months. */
  onExtend?: (side: 'start' | 'end') => void
  onSelectEvent: (e: CalendarEvent) => void
  onSelectSlot: (start: Date) => void
}

const monthKey = (m: Date) => format(m, 'yyyy-MM')

/** How many screens from an edge before the window grows. Generous, so growth happens
 *  about two years out, long before a normal scroll could reach the end. */
const EXTEND_SCREENS = 3

export function MonthView({
  window: win,
  initialMonth,
  events,
  weekStartsOn,
  scrollRequest,
  onVisibleMonthChange,
  onExtend,
  onSelectEvent,
  onSelectSlot,
}: Props) {
  const labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const ordered = weekStartsOn === 1 ? [...labels.slice(1), labels[0]] : labels
  const months = useMemo(() => monthsIn(win), [win])

  const scroller = useRef<HTMLDivElement>(null)
  const frame = useRef(0)
  const visible = useRef(initialMonth.getTime())
  // Mirrors `visible` for rendering: only months near it draw their cells. State, so it
  // re-renders -- but it only changes when the month in view does, not per scroll frame.
  const [visibleMonth, setVisibleMonth] = useState(initialMonth)
  // Set when we have asked for more months and they have not arrived yet, so a burst of
  // scroll events adds one batch, not one per event.
  const extending = useRef(false)
  const prev = useRef<{ first: number; height: number } | null>(null)
  // Callbacks change identity every render; the scroll listener must not be re-bound
  // each time (a re-bind mid-fling drops events), so it reads them through a ref.
  const cb = useRef({ onVisibleMonthChange, onExtend })
  cb.current = { onVisibleMonthChange, onExtend }

  const blockFor = (m: Date | number) =>
    scroller.current?.querySelector<HTMLElement>(`[data-month="${monthKey(new Date(m))}"]`) ?? null

  // Every block is the same height, so "which boundary is next" is a division.
  const { rest, scrollTo } = useLightSnap(scroller, {
    axis: 'y',
    measure: () => {
      const el = scroller.current
      const blocks = el?.querySelectorAll<HTMLElement>('[data-month]')
      if (!el || !blocks || blocks.length === 0) return null
      return {
        size: blocks[0].offsetHeight || el.clientHeight,
        count: blocks.length,
        at: (i) => blocks[i].offsetTop,
      }
    },
  })

  // Before paint, so there is never a frame showing the wrong scroll position. Handles
  // two cases: opening on the right month, and months being added above the viewport.
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    extending.current = false
    const first = months[0].getTime()
    if (!prev.current) {
      const target = blockFor(initialMonth)
      if (target) el.scrollTop = target.offsetTop
      // The snap measured its starting point before this jump, in an earlier effect.
      rest.current = el.scrollTop
    } else if (first < prev.current.first) {
      // Months were prepended. Everything the user is looking at just moved down by
      // the height we added; move the scroll position with it or the page jumps.
      const added = el.scrollHeight - prev.current.height
      el.scrollTop += added
      rest.current += added
    }
    prev.current = { first, height: el.scrollHeight }
    // initialMonth is deliberately not a dependency: it only matters on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months])

  // Declared after the effect above so that when a request arrives in the same commit as
  // newly prepended months, the position has already been corrected before we scroll.
  useLayoutEffect(() => {
    if (!scrollRequest) return
    const target = blockFor(scrollRequest.month)
    if (!target) return
    scrollTo(target.offsetTop)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollRequest])

  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return

    // The height the current scroll position was laid out for; see check().
    let sizedFor = el.clientHeight

    const check = () => {
      frame.current = 0
      const h = el.clientHeight
      if (h === 0) return
      // The scroller just changed size and the ResizeObserver has not re-pinned yet, so
      // scrollTop still belongs to the old block height. Reading the month from it here
      // was how a fresh load (the people bar arriving shrinks the scroller) opened one or
      // two months late: this ran first, and the re-pin then pinned the wrong month.
      if (h !== sizedFor) return
      // Every block is the same height, so the month in view is the one whose span
      // holds the middle of the viewport -- "the one most on screen".
      const blocks = el.querySelectorAll<HTMLElement>('[data-month]')
      // Blocks are a peek shorter than the screen (see .month in calendar.css), so step by
      // a block's own height, not the scroller's.
      const bh = blocks[0]?.offsetHeight || h
      const index = Math.min(blocks.length - 1, Math.max(0, Math.floor((el.scrollTop + h / 2) / bh)))
      const key = blocks[index]?.dataset.month
      if (key) {
        const [y, m] = key.split('-').map(Number)
        const month = new Date(y, m - 1, 1)
        if (month.getTime() !== visible.current) {
          visible.current = month.getTime()
          setVisibleMonth(month)
          cb.current.onVisibleMonthChange?.(month)
        }
      }
      if (!extending.current) {
        const toEnd = el.scrollHeight - el.scrollTop - h
        if (el.scrollTop < h * EXTEND_SCREENS) {
          extending.current = true
          cb.current.onExtend?.('start')
        } else if (toEnd < h * EXTEND_SCREENS) {
          extending.current = true
          cb.current.onExtend?.('end')
        }
      }
    }

    // rAF-throttled: scroll fires far more often than the screen repaints.
    const onScroll = () => {
      if (!frame.current) frame.current = requestAnimationFrame(check)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    // Rotating the wall display or resizing the window changes the block height, which
    // would leave scrollTop pointing between months. Re-pin the month we were on.
    const ro =
      typeof ResizeObserver === 'function'
        ? new ResizeObserver(() => {
            const target = blockFor(visible.current)
            if (target) el.scrollTop = target.offsetTop
            rest.current = el.scrollTop
            sizedFor = el.clientHeight
          })
        : null
    ro?.observe(el)

    onScroll()
    return () => {
      el.removeEventListener('scroll', onScroll)
      ro?.disconnect()
      if (frame.current) cancelAnimationFrame(frame.current)
      frame.current = 0
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="monthscroll" ref={scroller}>
      {months.map((month) => (
        <MonthBlock
          key={monthKey(month)}
          month={month}
          full={Math.abs(differenceInCalendarMonths(month, visibleMonth)) <= FULL_RENDER_PAD}
          ordered={ordered}
          weekStartsOn={weekStartsOn}
          events={events}
          onSelectEvent={onSelectEvent}
          onSelectSlot={onSelectSlot}
        />
      ))}
    </div>
  )
}

interface BlockProps {
  month: Date
  /** False for months far from the one in view: same height, no cells. */
  full: boolean
  ordered: string[]
  weekStartsOn: 0 | 1
  events: CalendarEvent[]
  onSelectEvent: (e: CalendarEvent) => void
  onSelectSlot: (start: Date) => void
}

function MonthBlock({ full, ...rest }: BlockProps) {
  if (!full) {
    // Keeps its place in the scroll (same .month height either way) so swapping
    // between this and a full block never moves anything. A few hundred cells per month
    // are only worth drawing for the months the user can actually reach.
    return (
      <section
        className="month month--placeholder"
        data-month={monthKey(rest.month)}
        aria-hidden
      >
        <div className="month__label">{format(rest.month, 'MMMM yyyy')}</div>
      </section>
    )
  }
  return <FullMonthBlock {...rest} />
}

function FullMonthBlock({
  month,
  ordered,
  weekStartsOn,
  events,
  onSelectEvent,
  onSelectSlot,
}: Omit<BlockProps, 'full'>) {
  const { days, start, end } = useMemo(() => rangeFor('month', month, weekStartsOn), [month, weekStartsOn])
  // Narrowed once per block so each of the ~35 cells filters a handful of events, not
  // everything in the seven-month window. Padded a day each side because all-day events
  // are UTC dates; overlapsDay does the exact per-cell test.
  const blockEvents = useMemo(() => {
    const from = addDays(start, -1)
    const to = addDays(end, 1)
    return events.filter((e) => new Date(e.start_at) < to && new Date(e.end_at) > from)
  }, [events, start, end])

  return (
    <section className="month" data-month={monthKey(month)} aria-label={format(month, 'MMMM yyyy')}>
      {/* Quiet on purpose: the toolbar title already names the month in view. This is
          only here so the seam between two months is visible while scrolling. */}
      <div className="month__label" aria-hidden>
        {format(month, 'MMMM yyyy')}
      </div>
      <div className="month__head">
        {ordered.map((l) => (
          <div key={l} className="month__headcell">
            {l}
          </div>
        ))}
      </div>
      <div
        className="month__grid"
        style={{ gridTemplateRows: `repeat(${days.length / 7}, minmax(0, 1fr))` }}
      >
        {days.map((day) => {
          const dayEvents = eventsOn(blockEvents, day)
          return (
            <div
              key={day.toISOString()}
              className="month__cell"
              data-today={isToday(day)}
              data-outside={!isSameMonth(day, month)}
            >
              {/* The whole cell adds an event, the same way an hour slot does in the
                  time grid. It sits behind the day number and the chips, so tapping
                  one of those still does its own thing. Before this, only the date
                  itself was tappable -- about 5% of the cell, which on a wall display
                  is a target you have to aim at rather than one you just hit. */}
              {/* Stays keyboard-reachable: the day number it replaces was a button,
                  and this is the only way to add an event on a given day from the
                  keyboard. The label carries the date, so the number itself is
                  hidden from screen readers rather than being read out twice. */}
              <button
                className="month__addlayer"
                onClick={() => onSelectSlot(atNoon(day))}
                aria-label={`Add event on ${format(day, 'MMMM d')}`}
              />
              <span className="month__daynum" aria-hidden>
                {format(day, 'd')}
              </span>
              <div className="month__events">
                {dayEvents.slice(0, 4).map((e) => (
                  <button
                    key={e.id}
                    className="chip chip--month"
                    style={{ background: e.color }}
                    onClick={() => onSelectEvent(e)}
                  >
                    {e.title}
                  </button>
                ))}
                {dayEvents.length > 4 && (
                  <span className="month__more">+{dayEvents.length - 4} more</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function atNoon(day: Date): Date {
  const d = new Date(day)
  d.setHours(12, 0, 0, 0)
  return d
}

function eventsOn(events: CalendarEvent[], day: Date): CalendarEvent[] {
  return events.filter((e) => overlapsDay(e, day))
}
