import { format, isToday } from 'date-fns'
import { useEffect, useRef } from 'react'
import type { CalendarEvent } from '../../api/types'
import { overlapsDay, startOfLocalDay } from './overlap'

interface Props {
  days: Date[]
  events: CalendarEvent[]
  dayStartHour: number
  dayEndHour: number
  use24h: boolean
  hourHeight: number
  onSelectEvent: (e: CalendarEvent) => void
  onSelectSlot: (start: Date) => void
}

/** One component drives Today (1 column), 3-Day (3) and Week (7) -- they differ only in
 *  how many day columns they render. */
export function TimeGridView({
  days,
  events,
  dayStartHour,
  dayEndHour,
  use24h,
  hourHeight,
  onSelectEvent,
  onSelectSlot,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const hours = Array.from({ length: dayEndHour - dayStartHour }, (_, i) => dayStartHour + i)

  useEffect(() => {
    const now = new Date()
    const offset = (now.getHours() - dayStartHour - 1) * hourHeight
    if (scrollRef.current && offset > 0) scrollRef.current.scrollTop = offset
  }, [dayStartHour, hourHeight])

  const allDay = events.filter((e) => e.all_day)

  return (
    <div className="timegrid" style={{ ['--days' as string]: days.length }}>
      <div className="timegrid__head">
        <div className="timegrid__gutter-head" />
        {days.map((day) => (
          <div key={day.toISOString()} className="timegrid__dayhead" data-today={isToday(day)}>
            <div className="timegrid__dayname">{format(day, 'EEE')}</div>
            <div className="timegrid__daynum">{format(day, 'd')}</div>
          </div>
        ))}
      </div>

      {allDay.length > 0 && (
        <div className="timegrid__allday">
          <div className="timegrid__gutter-head">all day</div>
          {days.map((day) => (
            <div key={day.toISOString()} className="timegrid__alldaycell">
              {allDay
                .filter((e) => overlapsDay(e, day))
                .map((e) => (
                  <button
                    key={e.id}
                    className="chip"
                    style={{ background: e.color }}
                    onClick={() => onSelectEvent(e)}
                  >
                    {e.title}
                  </button>
                ))}
            </div>
          ))}
        </div>
      )}

      <div className="timegrid__body" ref={scrollRef}>
        <div className="timegrid__gutter">
          {hours.map((h) => (
            <div key={h} className="timegrid__hourlabel" style={{ height: hourHeight }}>
              {formatHour(h, use24h)}
            </div>
          ))}
        </div>
        {days.map((day) => (
          <div key={day.toISOString()} className="timegrid__col" data-today={isToday(day)}>
            {hours.map((h) => (
              <button
                key={h}
                className="timegrid__slot"
                style={{ height: hourHeight }}
                aria-label={`Add event ${format(day, 'EEE d')} ${formatHour(h, use24h)}`}
                onClick={() => onSelectSlot(withHour(day, h))}
              />
            ))}
            {layout(events.filter((e) => !e.all_day && overlapsDay(e, day)), day, hourHeight).map(
              ({ event, top, height, left, width }) => (
                <button
                  key={event.id}
                  className="event-block"
                  style={{
                    top: top - dayStartHour * hourHeight,
                    height,
                    left: `${left}%`,
                    width: `${width}%`,
                    background: event.color,
                  }}
                  onClick={() => onSelectEvent(event)}
                >
                  <span className="event-block__title">{event.title}</span>
                  <span className="event-block__time">
                    {formatTime(new Date(event.start_at), use24h)}
                  </span>
                </button>
              ),
            )}
            {isToday(day) && <NowLine dayStartHour={dayStartHour} hourHeight={hourHeight} />}
          </div>
        ))}
      </div>
    </div>
  )
}

function NowLine({ dayStartHour, hourHeight }: { dayStartHour: number; hourHeight: number }) {
  const now = new Date()
  const top = (now.getHours() + now.getMinutes() / 60 - dayStartHour) * hourHeight
  if (top < 0) return null
  return <div className="nowline" style={{ top }} />
}

function withHour(day: Date, hour: number): Date {
  const d = new Date(day)
  d.setHours(hour, 0, 0, 0)
  return d
}

interface Positioned {
  event: CalendarEvent
  top: number
  height: number
  left: number
  width: number
}

/** Side-by-side placement for events that overlap in time, so nothing is hidden behind
 *  something else on a wall display nobody can hover. */
function layout(events: CalendarEvent[], day: Date, hourHeight: number): Positioned[] {
  const dayStart = startOfLocalDay(day)

  const spans = events
    .map((event) => {
      const s = new Date(event.start_at)
      const e = new Date(event.end_at)
      const startH = Math.max(0, (s.getTime() - dayStart.getTime()) / 3_600_000)
      const endH = Math.min(24, (e.getTime() - dayStart.getTime()) / 3_600_000)
      return { event, startH, endH: Math.max(endH, startH + 0.25) }
    })
    .sort((a, b) => a.startH - b.startH || b.endH - a.endH)

  const columns: number[] = []
  const placed = spans.map((span) => {
    let col = columns.findIndex((endsAt) => endsAt <= span.startH)
    if (col === -1) {
      col = columns.length
      columns.push(span.endH)
    } else {
      columns[col] = span.endH
    }
    return { ...span, col }
  })

  const total = Math.max(1, columns.length)
  return placed.map((p) => ({
    event: p.event,
    top: p.startH * hourHeight,
    height: Math.max(26, (p.endH - p.startH) * hourHeight - 2),
    left: (p.col / total) * 100,
    width: (1 / total) * 100 - 1,
  }))
}

export function formatHour(hour: number, use24h: boolean): string {
  if (use24h) return `${String(hour).padStart(2, '0')}:00`
  const h = hour % 12 === 0 ? 12 : hour % 12
  return `${h}${hour < 12 ? 'a' : 'p'}`
}

export function formatTime(d: Date, use24h: boolean): string {
  return format(d, use24h ? 'HH:mm' : 'h:mma').toLowerCase()
}
