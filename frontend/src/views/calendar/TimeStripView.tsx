import { differenceInCalendarDays, format, isToday } from 'date-fns'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CalendarEvent } from '../../api/types'
import { useLightSnap } from '../../hooks/useLightSnap'
import { DAY_FULL_PAD, firstVisibleIndex, spanOf, stripStartFor, type DayWindow, type StripKind, daysIn } from './dateRange'
import { AllDayChips, DayColumn, HourGutter } from './TimeGridView'

/** Ask the strip to bring a day to the first column. `id` makes repeat requests for the
 *  same day (tapping Today twice) distinct. */
export interface StripScrollRequest {
  day: Date
  id: number
}

interface Props {
  kind: StripKind
  window: DayWindow
  /** The day to open in the first column. Read once, on mount; after that the user (or a
   *  scroll request) owns the scroll position. */
  initialStart: Date
  weekStartsOn: 0 | 1
  events: CalendarEvent[]
  dayStartHour: number
  dayEndHour: number
  use24h: boolean
  hourHeight: number
  scrollRequest?: StripScrollRequest | null
  /** The first fully visible day changed. */
  onVisibleStartChange?: (day: Date) => void
  /** The user scrolled close to one end of the window; the parent should add days. */
  onExtend?: (side: 'start' | 'end') => void
  onSelectEvent: (e: CalendarEvent) => void
  onSelectSlot: (start: Date) => void
}

/** How many screens from an edge before the window grows. Generous, so growth happens
 *  months out, long before a normal scroll could reach the end. */
const EXTEND_SCREENS = 3

/**
 * Week and 3 Day: the day columns are one horizontal strip that scrolls forever. One
 * scroller owns both axes so the header, all-day band and hour gutter can be `sticky`
 * against it -- they then move with the columns on one axis and stay put on the other,
 * with no scroll syncing between separate elements to drift.
 */
export function TimeStripView({
  kind,
  window: win,
  initialStart,
  weekStartsOn,
  events,
  dayStartHour,
  dayEndHour,
  use24h,
  hourHeight,
  scrollRequest,
  onVisibleStartChange,
  onExtend,
  onSelectEvent,
  onSelectSlot,
}: Props) {
  const span = spanOf(kind)
  const days = useMemo(() => daysIn(win), [win])
  const hours = useMemo(
    () => Array.from({ length: dayEndHour - dayStartHour }, (_, i) => dayStartHour + i),
    [dayStartHour, dayEndHour],
  )

  const scroller = useRef<HTMLDivElement>(null)
  const frame = useRef(0)
  const visible = useRef(initialStart.getTime())
  // Mirrors `visible` for rendering: only columns near it draw their slots. State, so it
  // re-renders -- but it only changes when the first visible day does, not per scroll frame.
  const [visibleStart, setVisibleStart] = useState(initialStart)
  // Set when we have asked for more days and they have not arrived yet, so a burst of
  // scroll events adds one batch, not one per event.
  const extending = useRef(false)
  const prev = useRef<{ first: number; width: number } | null>(null)
  // Callbacks change identity every render; the scroll listener must not be re-bound
  // each time (a re-bind mid-fling drops events), so it reads them through a ref.
  const cb = useRef({ onVisibleStartChange, onExtend })
  cb.current = { onVisibleStartChange, onExtend }
  const daysRef = useRef(days)
  daysRef.current = days

  /** Measured, not computed: the column width is CSS (`--col`), and the snap and the
   *  position maths must agree with what was actually laid out, fractions included. */
  const colWidth = () =>
    scroller.current?.querySelector<HTMLElement>('.timegrid__col')?.getBoundingClientRect().width ?? 0
  const indexOf = (day: Date | number) => differenceInCalendarDays(new Date(day), daysRef.current[0])

  const { rest, scrollTo } = useLightSnap(scroller, {
    axis: 'x',
    measure: () => {
      const size = colWidth()
      // Column i sits at i * size in the content, with the sticky gutter overlaying the
      // first `gutter` pixels -- so scrolling to i * size puts column i first in view.
      if (size <= 0) return null
      // Today's default view (its week, or today first) gets the stronger home pull.
      // Worked out at each settle rather than once, so a wall screen left on overnight
      // moves home to the new day.
      const h = indexOf(stripStartFor(kind, new Date(), weekStartsOn))
      const count = daysRef.current.length
      return { size, count, at: (i) => i * size, home: h >= 0 && h < count ? h * size : null }
    },
  })

  // Open on the right day, and correct for days being added before the viewport. Before
  // paint, so there is never a frame showing the wrong position.
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return
    extending.current = false
    const first = days[0].getTime()
    if (!prev.current) {
      el.scrollLeft = indexOf(initialStart) * colWidth()
      rest.current = el.scrollLeft
    } else if (first < prev.current.first) {
      // Days were prepended. Everything the user is looking at just moved right by the
      // width we added; move the scroll position with it or the view jumps.
      const added = el.scrollWidth - prev.current.width
      el.scrollLeft += added
      rest.current += added
    }
    prev.current = { first, width: el.scrollWidth }
    // initialStart is deliberately not a dependency: it only matters on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days])

  // Declared after the effect above so that when a request arrives in the same commit as
  // newly prepended days, the position has already been corrected before we scroll.
  useLayoutEffect(() => {
    if (!scrollRequest) return
    const width = colWidth()
    const index = indexOf(scrollRequest.day)
    if (width > 0 && index >= 0 && index < daysRef.current.length) scrollTo(index * width)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollRequest])

  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return

    // The width the current scroll position was laid out for; see check().
    let sizedFor = el.clientWidth

    const check = () => {
      frame.current = 0
      const w = el.clientWidth
      if (w === 0) return
      // The scroller just changed size and the ResizeObserver has not re-pinned yet, so
      // scrollLeft still belongs to the old column width. Reading the day from it here
      // was how Month opened on the wrong period after a fresh load (the people bar
      // arriving shrinks the scroller): this ran first, and the re-pin then pinned it.
      if (w !== sizedFor) return
      const cw = colWidth()
      const all = daysRef.current
      if (cw === 0) return
      const index = Math.min(all.length - 1, firstVisibleIndex(el.scrollLeft, cw))
      const day = all[index]
      if (day.getTime() !== visible.current) {
        visible.current = day.getTime()
        setVisibleStart(day)
        cb.current.onVisibleStartChange?.(day)
      }
      if (!extending.current) {
        const toEnd = el.scrollWidth - el.scrollLeft - w
        if (el.scrollLeft < w * EXTEND_SCREENS) {
          extending.current = true
          cb.current.onExtend?.('start')
        } else if (toEnd < w * EXTEND_SCREENS) {
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

    // Rotating the wall display or resizing the window changes the column width, which
    // would leave scrollLeft pointing between days. Re-pin the day we were on.
    const ro =
      typeof ResizeObserver === 'function'
        ? new ResizeObserver(() => {
            const cw = colWidth()
            if (cw > 0) el.scrollLeft = indexOf(visible.current) * cw
            rest.current = el.scrollLeft
            sizedFor = el.clientWidth
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

  // Opens near the current hour, or the start of the day if that is already behind us.
  useEffect(() => {
    const offset = (new Date().getHours() - dayStartHour - 1) * hourHeight
    if (scroller.current && offset > 0) scroller.current.scrollTop = offset
  }, [dayStartHour, hourHeight])

  const hasAllDay = events.some((e) => e.all_day)
  const visibleIndex = differenceInCalendarDays(visibleStart, days[0])
  const isFull = (i: number) => i >= visibleIndex - DAY_FULL_PAD && i < visibleIndex + span + DAY_FULL_PAD

  return (
    <div
      className="timestrip"
      ref={scroller}
      data-kind={kind}
      style={{ ['--days' as string]: span, ['--n' as string]: days.length }}
    >
      <div className="timestrip__ruler">
        <div className="timestrip__inner">
          {/* One sticky block so the header and the all-day band stay together at the top
              without either needing to know the other's height. */}
          <div className="timestrip__top">
            <div className="timestrip__row timestrip__row--head">
              <div className="timegrid__gutter-head" />
              {days.map((day) => (
                <div key={day.getTime()} className="timegrid__dayhead" data-today={isToday(day)}>
                  <div className="timegrid__dayname">{format(day, 'EEE')}</div>
                  <div className="timegrid__daynum">{format(day, 'd')}</div>
                </div>
              ))}
            </div>
            {hasAllDay && (
              <div className="timestrip__row timestrip__row--allday">
                <div className="timegrid__gutter-head">all day</div>
                {days.map((day, i) => (
                  <div key={day.getTime()} className="timegrid__alldaycell">
                    {isFull(i) && (
                      <AllDayChips day={day} events={events} onSelectEvent={onSelectEvent} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="timestrip__row timestrip__row--body">
            <HourGutter hours={hours} hourHeight={hourHeight} use24h={use24h} />
            {days.map((day, i) => (
              <DayColumn
                key={day.getTime()}
                day={day}
                events={events}
                hours={hours}
                dayStartHour={dayStartHour}
                hourHeight={hourHeight}
                use24h={use24h}
                placeholder={!isFull(i)}
                onSelectEvent={onSelectEvent}
                onSelectSlot={onSelectSlot}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
