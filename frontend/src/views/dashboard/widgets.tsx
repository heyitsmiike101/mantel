import { addDays, format, isSameDay, isSameMonth, startOfMonth, startOfWeek } from 'date-fns'
import { useEffect, useState } from 'react'
import { useEvents, useUsers } from '../../api/hooks'
import type { CalendarEvent } from '../../api/types'
import { overlapsDay } from '../calendar/overlap'

export interface WidgetProps {
  config: Record<string, unknown>
  onConfigChange: (config: Record<string, unknown>) => void
  onOpenEvent: (event: CalendarEvent) => void
  onNewEvent: (start: Date) => void
}

interface WidgetDef {
  component: (props: WidgetProps) => React.ReactNode
  label: string
}

function num(config: Record<string, unknown>, key: string, fallback: number): number {
  const v = config[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback
}

// ------------------------------ Upcoming events ------------------------------

function UpcomingEvents({ config, onOpenEvent, onNewEvent }: WidgetProps) {
  const days = num(config, 'days', 7)
  const max = num(config, 'max_items', 12)
  // Anchored to midnight so the query key is stable across renders; "upcoming" is then
  // applied client-side against the actual current time.
  const dayStart = startOfToday()
  const { data: events = [] } = useEvents(dayStart, addDays(dayStart, days))
  const now = new Date()
  const visible = events.filter((e) => new Date(e.end_at) > now).slice(0, max)

  return (
    <>
      <div className="widget__head">
        <h3>Next {days} days</h3>
        <button className="iconbtn iconbtn--primary" onClick={() => onNewEvent(nextHour())}>
          +
        </button>
      </div>
      {visible.length === 0 && <p className="widget__empty">Nothing coming up.</p>}
      <ul className="agenda">
        {visible.map((e) => (
          <li key={e.id} className="agenda__row">
            <span className="agenda__dot" style={{ background: e.color }} />
            <button className="agenda__main" onClick={() => onOpenEvent(e)}>
              <span className="agenda__title">{e.title}</span>
              <span className="agenda__when">{whenLabel(e)}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

// ------------------------------- Today agenda --------------------------------

function TodayAgenda({ onOpenEvent, onNewEvent }: WidgetProps) {
  const { data: users = [] } = useUsers()
  const today = new Date()
  const dayStart = startOfToday()
  const { data: events = [] } = useEvents(dayStart, addDays(dayStart, 1))

  const columns = users.length > 0 ? users : [{ id: -1, name: 'Family', color: '#64748b' }]

  return (
    <>
      <div className="widget__head">
        <h3>{format(today, 'EEEE, MMMM d')}</h3>
        <button className="iconbtn iconbtn--primary" onClick={() => onNewEvent(nextHour())}>
          +
        </button>
      </div>
      <div className="people">
        {columns.map((u) => {
          const mine = events.filter((e) => (u.id === -1 ? true : e.user_id === u.id))
          return (
            <div key={u.id} className="people__col">
              <div className="people__name" style={{ borderColor: u.color }}>
                {u.name}
              </div>
              {mine.length === 0 && <div className="people__free">Free</div>}
              {mine.map((e) => (
                <button
                  key={e.id}
                  className="chip"
                  style={{ background: e.color }}
                  onClick={() => onOpenEvent(e)}
                >
                  {e.all_day ? '' : `${format(new Date(e.start_at), 'h:mm')} `}
                  {e.title}
                </button>
              ))}
            </div>
          )
        })}
      </div>
    </>
  )
}

// ---------------------------------- Clock ------------------------------------

function Clock({ config }: WidgetProps) {
  const showSeconds = config.show_seconds === true
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), showSeconds ? 1000 : 20_000)
    return () => clearInterval(timer)
  }, [showSeconds])

  return (
    <div className="clock">
      <div className="clock__time">{format(now, showSeconds ? 'h:mm:ss' : 'h:mm')}</div>
      <div className="clock__date">{format(now, 'EEEE, MMMM d')}</div>
    </div>
  )
}

// ------------------------------- Mini month ----------------------------------

function MiniMonth({ onNewEvent }: WidgetProps) {
  const today = new Date()
  const gridStart = startOfWeek(startOfMonth(today), { weekStartsOn: 0 })
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const { data: events = [] } = useEvents(gridStart, addDays(gridStart, 42))

  return (
    <>
      <div className="widget__head">
        <h3>{format(today, 'MMMM yyyy')}</h3>
      </div>
      <div className="minimonth">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((l, i) => (
          <div key={i} className="minimonth__label">
            {l}
          </div>
        ))}
        {days.map((d) => {
          const has = events.some((e) => overlapsDay(e, d))
          return (
            <button
              key={d.toISOString()}
              className="minimonth__day"
              data-today={isSameDay(d, today)}
              data-outside={!isSameMonth(d, today)}
              onClick={() => onNewEvent(atNoon(d))}
            >
              {format(d, 'd')}
              {has && <span className="minimonth__dot" />}
            </button>
          )
        })}
      </div>
    </>
  )
}

// ---------------------------------- Note -------------------------------------

function Note({ config, onConfigChange }: WidgetProps) {
  const [text, setText] = useState(typeof config.text === 'string' ? config.text : '')
  return (
    <>
      <div className="widget__head">
        <h3>Family note</h3>
      </div>
      <textarea
        className="note"
        value={text}
        placeholder="Anything the house should know…"
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onConfigChange({ ...config, text })}
      />
    </>
  )
}

// -------------------------------- registry -----------------------------------

export const WIDGETS: Record<string, WidgetDef> = {
  upcoming_events: { component: UpcomingEvents, label: 'Upcoming events' },
  today_agenda: { component: TodayAgenda, label: 'Today by person' },
  clock: { component: Clock, label: 'Clock and date' },
  mini_month: { component: MiniMonth, label: 'Month at a glance' },
  note: { component: Note, label: 'Family note' },
}

/** Midnight today. Used as a query anchor so React Query keys stay stable. */
function startOfToday(): Date {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function nextHour(): Date {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}

function atNoon(d: Date): Date {
  const out = new Date(d)
  out.setHours(12, 0, 0, 0)
  return out
}

function whenLabel(e: CalendarEvent): string {
  const start = new Date(e.start_at)
  const today = new Date()
  const dayPart = isSameDay(start, today)
    ? 'Today'
    : isSameDay(start, addDays(today, 1))
      ? 'Tomorrow'
      : format(start, 'EEE MMM d')
  return e.all_day ? dayPart : `${dayPart} · ${format(start, 'h:mm a')}`
}
