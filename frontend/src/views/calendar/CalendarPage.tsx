import { addMonths, differenceInCalendarMonths, format, isSameMonth, startOfMonth } from 'date-fns'
import { useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { useEvents, useSettings, useUsers } from '../../api/hooks'
import type { CalendarEvent } from '../../api/types'
import { EventModal } from '../../components/EventModal'
import { usePersonFilter } from '../../hooks/usePersonFilter'
import { useSwipe } from '../../hooks/useSwipe'
import { MonthView, type MonthScrollRequest } from './MonthView'
import { TimeGridView } from './TimeGridView'
import {
  MONTH_EXTEND_BATCH,
  eventsRangeAround,
  extendWindow,
  isViewKind,
  monthWindow,
  rangeFor,
  step,
  windowHas,
  type MonthWindow,
} from './dateRange'

/** Mirrors the --scale values in global.css: taller hour rows on a wall display keep
 *  short events big enough to tap. */
const SCALE_FACTOR: Record<string, number> = { normal: 1, large: 1.2, wall: 1.45 }

/** The phone shows one nav entry for the calendar, so the four views need a home
 *  on the page itself. Hidden above phone size, where the nav still lists them. */
const VIEW_TABS = [
  { kind: 'today', label: 'Day' },
  { kind: '3day', label: '3 Day' },
  { kind: 'week', label: 'Week' },
  { kind: 'month', label: 'Month' },
] as const

export function CalendarPage() {
  const { view } = useParams()
  const navigate = useNavigate()
  const { data: settings } = useSettings()
  const { data: users = [] } = useUsers()
  const { toggle, showEveryone, isVisible, anyHidden } = usePersonFilter()
  const [anchor, setAnchor] = useState(() => new Date())
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  const [creatingAt, setCreatingAt] = useState<Date | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const weekStartsOn = (settings?.first_day_of_week === 1 ? 1 : 0) as 0 | 1
  const kind = isViewKind(view) ? view : null
  const range = rangeFor(kind ?? 'week', anchor, weekStartsOn)

  // Month view scrolls through a window of months instead of showing one. The window is
  // wide so it rarely grows; events are fetched only around the month in view.
  const [monthWin, setMonthWin] = useState<MonthWindow>(() => monthWindow(anchor))
  // `epoch` remounts the scroller when we jump somewhere the window cannot reach.
  const [monthOpen, setMonthOpen] = useState(() => ({ epoch: 0, initial: startOfMonth(anchor) }))
  const [scrollReq, setScrollReq] = useState<MonthScrollRequest | null>(null)
  const reqId = useRef(0)
  const [prevKind, setPrevKind] = useState(kind)
  if (kind !== prevKind) {
    setPrevKind(kind)
    // Coming back to month view from Week/Day: open on wherever the anchor is now.
    if (kind === 'month') openMonthAt(anchor)
  }
  function openMonthAt(date: Date) {
    setMonthWin(monthWindow(date))
    setMonthOpen((o) => ({ epoch: o.epoch + 1, initial: startOfMonth(date) }))
    setScrollReq(null)
  }

  // Keyed on the visible month (the anchor's month), so the range -- and the query --
  // changes once per month crossed, not per scroll frame.
  const fetchRange = kind === 'month' ? eventsRangeAround(anchor, weekStartsOn) : range
  const { data: fetched, isLoading } = useEvents(fetchRange.start, fetchRange.end)
  // A new range is a new query with no data yet; showing nothing while it loads would
  // blank every chip on screen each time the user scrolls into a new month.
  const [shown, setShown] = useState(fetched)
  if (fetched && fetched !== shown) setShown(fetched)
  const allEvents = fetched ?? (kind === 'month' ? shown : undefined) ?? []
  const events = allEvents.filter((e) => isVisible(e.user_id))

  // Where the last button press is scrolling to. The anchor only moves once a smooth
  // scroll gets there, so three quick taps on › counted from the anchor would all land
  // on the same month. It expires after a second so that if the user grabs the screen
  // mid-scroll and goes elsewhere, the next tap counts from what they are looking at.
  const pending = useRef<{ month: Date; at: number } | null>(null)
  const pendingMonth = () =>
    pending.current && Date.now() - pending.current.at < 1000 ? pending.current.month : null
  const scrollToMonth = (month: Date) => {
    pending.current = { month, at: Date.now() }
    setScrollReq({ month, id: ++reqId.current })
  }
  const stepMonth = (dir: 1 | -1) => {
    const target = addMonths(pendingMonth() ?? startOfMonth(anchor), dir)
    if (windowHas(monthWin, target)) return scrollToMonth(target)
    const side = target < monthWin.first ? 'start' : 'end'
    const edge = side === 'start' ? monthWin.first : monthWin.last
    // A step or two past the edge just grows the window; a long way past it (Today
    // from years away) starts over there rather than rendering every month between.
    if (Math.abs(differenceInCalendarMonths(target, edge)) > MONTH_EXTEND_BATCH) return openMonthAt(target)
    setMonthWin((w) => extendWindow(w, side))
    scrollToMonth(target)
  }
  const goToday = () => {
    const now = new Date()
    setAnchor(now)
    if (kind !== 'month') return
    if (windowHas(monthWin, now)) scrollToMonth(startOfMonth(now))
    else openMonthAt(now)
  }
  const goStep = (dir: 1 | -1) => {
    if (kind === 'month') stepMonth(dir)
    else setAnchor((a) => step(kind ?? 'week', a, dir))
  }
  const onVisibleMonthChange = (month: Date) => {
    if (pending.current && isSameMonth(month, pending.current.month)) pending.current = null
    // Keep the anchor on the month in view so Week/Day open somewhere sensible. In the
    // current month that is today rather than the 1st.
    setAnchor(isSameMonth(month, new Date()) ? new Date() : month)
  }
  const swipe = useSwipe(goStep)

  // e.g. /calendar/fortnight. Same landing place as the app's front door.
  if (!kind) return <Navigate to="/calendar/today" replace />

  const openEvent = (e: CalendarEvent) => {
    setEditing(e)
    setCreatingAt(null)
    setModalOpen(true)
  }
  const openSlot = (start: Date) => {
    setEditing(null)
    setCreatingAt(start)
    setModalOpen(true)
  }

  return (
    <div className="calpage">
      <header className="calpage__bar">
        <div className="calpage__titlewrap">
          <h1 className="calpage__title">{titleFor(kind, range.start, range.end, anchor)}</h1>
          {isLoading && <span className="calpage__loading">…</span>}
        </div>
        {/* In the toolbar, beside the controls rather than the title, so they don't slide
            sideways every time the title changes length. A phone wraps them onto a
            second line of the same bar. */}
        {users.length > 0 && (
          <div className="peoplefilter">
            {users.map((u) => {
              const shown = isVisible(u.id)
              return (
                <button
                  key={u.id}
                  className="personchip"
                  data-hidden={!shown}
                  aria-pressed={shown}
                  style={shown ? { background: u.color, borderColor: u.color } : undefined}
                  onClick={() => toggle(u.id)}
                  title={shown ? `Hide ${u.name}'s events` : `Show ${u.name}'s events`}
                >
                  {u.avatar_emoji && <span aria-hidden>{u.avatar_emoji}</span>}
                  {u.name}
                </button>
              )
            })}
            {anyHidden && (
              <button className="personchip personchip--all" onClick={showEveryone}>
                Show everyone
              </button>
            )}
          </div>
        )}
        <button className="iconbtn" onClick={goToday}>
          Today
        </button>
        {/* One joined control, so the two arrows read as a pair and a thumb can find
            either without crossing the Today button. */}
        <div className="segmented">
          <button className="iconbtn" onClick={() => goStep(-1)} aria-label="Previous">
            ‹
          </button>
          <button className="iconbtn" onClick={() => goStep(1)} aria-label="Next">
            ›
          </button>
        </div>
        <button className="iconbtn iconbtn--primary" onClick={() => openSlot(nextHour())} aria-label="Add event">
          +
        </button>
      </header>

      <div className="viewtabs">
        {VIEW_TABS.map((t) => (
          <button
            key={t.kind}
            className="viewtabs__tab"
            aria-current={kind === t.kind ? 'page' : undefined}
            onClick={() => navigate(`/calendar/${t.kind}`)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="calpage__body" {...swipe}>
        {kind === 'month' ? (
          <MonthView
            key={monthOpen.epoch}
            window={monthWin}
            initialMonth={monthOpen.initial}
            events={events}
            weekStartsOn={weekStartsOn}
            scrollRequest={scrollReq}
            onVisibleMonthChange={onVisibleMonthChange}
            onExtend={(side) => setMonthWin((w) => extendWindow(w, side))}
            onSelectEvent={openEvent}
            onSelectSlot={openSlot}
          />
        ) : (
          <TimeGridView
            days={range.days}
            events={events}
            dayStartHour={settings?.day_start_hour ?? 7}
            dayEndHour={settings?.day_end_hour ?? 22}
            use24h={settings?.time_format_24h ?? false}
            hourHeight={64 * SCALE_FACTOR[settings?.display_scale ?? 'normal']}
            onSelectEvent={openEvent}
            onSelectSlot={openSlot}
          />
        )}
      </div>

      {modalOpen && (
        <EventModal
          event={editing}
          defaultStart={creatingAt}
          onClose={() => {
            setModalOpen(false)
            setEditing(null)
            setCreatingAt(null)
          }}
        />
      )}
    </div>
  )
}

function nextHour(): Date {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}

function titleFor(kind: string, start: Date, end: Date, anchor: Date): string {
  if (kind === 'month') return format(anchor, 'MMMM yyyy')
  if (kind === 'today') return format(start, 'EEEE, MMMM d')
  const last = new Date(end.getTime() - 1)
  return isSameMonth(start, last)
    ? `${format(start, 'MMM d')} – ${format(last, 'd, yyyy')}`
    : `${format(start, 'MMM d')} – ${format(last, 'MMM d, yyyy')}`
}
