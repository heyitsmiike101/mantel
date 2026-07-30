import { format, isSameMonth, isToday } from 'date-fns'
import type { CalendarEvent } from '../../api/types'
import { overlapsDay } from './overlap'

interface Props {
  days: Date[]
  anchor: Date
  events: CalendarEvent[]
  weekStartsOn: 0 | 1
  onSelectEvent: (e: CalendarEvent) => void
  onSelectSlot: (start: Date) => void
}

export function MonthView({
  days,
  anchor,
  events,
  weekStartsOn,
  onSelectEvent,
  onSelectSlot,
}: Props) {
  const labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const ordered = weekStartsOn === 1 ? [...labels.slice(1), labels[0]] : labels

  return (
    <div className="month">
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
          const dayEvents = eventsOn(events, day)
          return (
            <div
              key={day.toISOString()}
              className="month__cell"
              data-today={isToday(day)}
              data-outside={!isSameMonth(day, anchor)}
            >
              <button
                className="month__daynum"
                onClick={() => onSelectSlot(atNoon(day))}
                aria-label={`Add event on ${format(day, 'MMMM d')}`}
              >
                {format(day, 'd')}
              </button>
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
    </div>
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
