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
