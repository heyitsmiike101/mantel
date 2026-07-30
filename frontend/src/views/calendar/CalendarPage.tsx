import { format, isSameMonth } from 'date-fns'
import { useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useEvents, useSettings, useUsers } from '../../api/hooks'
import type { CalendarEvent } from '../../api/types'
import { EventModal } from '../../components/EventModal'
import { usePersonFilter } from '../../hooks/usePersonFilter'
import { useSwipe } from '../../hooks/useSwipe'
import { MonthView } from './MonthView'
import { TimeGridView } from './TimeGridView'
import { isViewKind, rangeFor, step } from './dateRange'

/** Mirrors the --scale values in global.css: taller hour rows on a wall display keep
 *  short events big enough to tap. */
const SCALE_FACTOR: Record<string, number> = { normal: 1, large: 1.2, wall: 1.45 }

export function CalendarPage() {
  const { view } = useParams()
  const { data: settings } = useSettings()
  const { data: users = [] } = useUsers()
  const { userIds, toggle, clear, showingEveryone } = usePersonFilter()
  const [anchor, setAnchor] = useState(() => new Date())
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  const [creatingAt, setCreatingAt] = useState<Date | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const weekStartsOn = (settings?.first_day_of_week === 1 ? 1 : 0) as 0 | 1
  const kind = isViewKind(view) ? view : null
  const range = rangeFor(kind ?? 'week', anchor, weekStartsOn)
  const { data: events = [], isLoading } = useEvents(range.start, range.end, userIds)
  const swipe = useSwipe((dir) => setAnchor((a) => step(kind ?? 'week', a, dir)))

  if (!kind) return <Navigate to="/calendar/week" replace />

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
    <div className="calpage" data-filtered={users.length > 1 ? 'true' : undefined}>
      <header className="calpage__bar">
        <button className="iconbtn" onClick={() => setAnchor((a) => step(kind, a, -1))} aria-label="Previous">
          ‹
        </button>
        <div className="calpage__titlewrap">
          <h1 className="calpage__title">{titleFor(kind, range.start, range.end, anchor)}</h1>
          {isLoading && <span className="calpage__loading">…</span>}
        </div>
        <button className="iconbtn" onClick={() => setAnchor(new Date())}>
          Today
        </button>
        <button className="iconbtn" onClick={() => setAnchor((a) => step(kind, a, 1))} aria-label="Next">
          ›
        </button>
        <button className="iconbtn iconbtn--primary" onClick={() => openSlot(nextHour())} aria-label="Add event">
          +
        </button>
      </header>

      {users.length > 1 && (
        <div className="peoplefilter">
          <button
            className="chipbtn"
            aria-current={showingEveryone ? 'page' : undefined}
            onClick={clear}
          >
            Everyone
          </button>
          {users.map((u) => {
            const on = userIds.includes(u.id)
            return (
              <button
                key={u.id}
                className="chipbtn chipbtn--person"
                aria-current={on ? 'page' : undefined}
                style={on ? { background: u.color, borderColor: u.color, color: '#0b1220' } : { borderColor: u.color }}
                onClick={() => toggle(u.id)}
              >
                <span className="chipbtn__dot" style={{ background: u.color }} />
                {u.name}
              </button>
            )
          })}
        </div>
      )}

      <div className="calpage__body" {...swipe}>
        {kind === 'month' ? (
          <MonthView
            days={range.days}
            anchor={anchor}
            events={events}
            weekStartsOn={weekStartsOn}
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
