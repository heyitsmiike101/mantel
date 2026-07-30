import { addDays, format, isSameDay, isSameMonth, startOfMonth, startOfWeek } from 'date-fns'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useEntityMutation, useEvents, useUsers, useWeather } from '../../api/hooks'
import type { SharedList } from '../../api/types'
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

function str(config: Record<string, unknown>, key: string, fallback = ''): string {
  const v = config[key]
  return typeof v === 'string' ? v : fallback
}

/** `user_ids` has always been advertised in the widget catalog; this is what
 *  finally reads it. An empty or missing list means everyone. */
function people(config: Record<string, unknown>): number[] {
  const v = config.user_ids
  return Array.isArray(v) ? v.filter((n): n is number => typeof n === 'number') : []
}

// ------------------------------ Upcoming events ------------------------------

function UpcomingEvents({ config, onOpenEvent, onNewEvent }: WidgetProps) {
  const days = num(config, 'days', 7)
  const max = num(config, 'max_items', 12)
  // Anchored to midnight so the query key is stable across renders; "upcoming" is then
  // applied client-side against the actual current time.
  const dayStart = startOfToday()
  const { data: events = [] } = useEvents(dayStart, addDays(dayStart, days), people(config))
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

function TodayAgenda({ config, onOpenEvent, onNewEvent }: WidgetProps) {
  const { data: users = [] } = useUsers()
  const today = new Date()
  const dayStart = startOfToday()
  const only = people(config)
  const { data: events = [] } = useEvents(dayStart, addDays(dayStart, 1), only)

  const shown = only.length ? users.filter((u) => only.includes(u.id)) : users
  const columns = shown.length > 0 ? shown : [{ id: -1, name: 'Family', color: '#64748b' }]

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

// --------------------------------- List --------------------------------------

function ListWidget({ config }: WidgetProps) {
  const listId = num(config, 'list_id', 0)
  const hideChecked = config.hide_checked === true
  const [text, setText] = useState('')

  const { data: lists = [] } = useQuery({
    queryKey: ['lists'],
    queryFn: () => api.get<SharedList[]>('/lists'),
    refetchInterval: 30_000,
  })

  const list = lists.find((l) => l.id === listId) ?? lists[0]

  const addItem = useEntityMutation(
    (body: { text: string }) => api.post(`/lists/${list?.id}/items`, body),
    ['lists'],
  )
  const toggle = useEntityMutation(
    ({ id, checked }: { id: number; checked: boolean }) =>
      api.patch(`/lists/${list?.id}/items/${id}`, { checked }),
    ['lists'],
  )

  if (!list) {
    return (
      <>
        <div className="widget__head">
          <h3>List</h3>
        </div>
        <p className="widget__empty">Create a list on the Lists page first.</p>
      </>
    )
  }

  const items = hideChecked ? list.items.filter((i) => !i.checked) : list.items

  const submit = () => {
    const value = text.trim()
    if (!value) return
    addItem.mutate({ text: value })
    setText('')
  }

  return (
    <>
      <div className="widget__head">
        <h3>
          {list.icon} {list.name}
        </h3>
        <span className="listcard__count">{list.item_count}</span>
      </div>

      <ul className="listcard__items">
        {items.slice(0, 12).map((item) => (
          <li key={item.id} className="listitem" data-checked={item.checked}>
            <button
              className="listitem__check"
              aria-label={item.checked ? `Uncheck ${item.text}` : `Check off ${item.text}`}
              style={item.color && !item.checked ? { borderColor: item.color } : undefined}
              onClick={() => toggle.mutate({ id: item.id, checked: !item.checked })}
            >
              {item.checked ? '✓' : ''}
            </button>
            <span className="listitem__text">{item.text}</span>
          </li>
        ))}
      </ul>
      {items.length === 0 && <p className="widget__empty">Nothing on this list.</p>}

      <div className="listcard__add">
        <input
          value={text}
          placeholder="Add an item"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        <button className="btn btn--primary" onClick={submit}>
          Add
        </button>
      </div>
    </>
  )
}

// -------------------------------- Weather ------------------------------------

/** Condition text -> emoji. Both providers hand back short English phrases, so one
 *  keyword table covers them. */
function weatherIcon(short: string | null | undefined, daytime = true): string {
  const t = (short ?? '').toLowerCase()
  if (t.includes('thunder')) return '⛈️'
  if (t.includes('snow') || t.includes('flurr')) return '🌨️'
  if (t.includes('sleet') || t.includes('freezing')) return '🧊'
  if (t.includes('rain') || t.includes('shower') || t.includes('drizzle')) return '🌧️'
  if (t.includes('fog') || t.includes('haze') || t.includes('mist')) return '🌫️'
  if (t.includes('wind')) return '💨'
  if (t.includes('cloud') || t.includes('overcast')) return '☁️'
  if (t.includes('partly') || t.includes('mostly sunny')) return daytime ? '⛅' : '☁️'
  if (t.includes('clear') || t.includes('sunny') || t.includes('fair'))
    return daytime ? '☀️' : '🌙'
  return daytime ? '🌤️' : '🌙'
}

function Weather({ config }: WidgetProps) {
  const { data, isLoading } = useWeather()
  const dayCount = num(config, 'days', 5)

  if (isLoading) return <p className="widget__empty">Loading…</p>
  if (!data?.available) {
    return (
      <>
        <div className="widget__head">
          <h3>Weather</h3>
        </div>
        <p className="widget__empty">{data?.reason ?? 'Weather is unavailable.'}</p>
      </>
    )
  }

  const c = data.current
  const unit = data.units === 'metric' ? 'C' : 'F'

  return (
    <>
      <div className="widget__head">
        <h3>{data.place ?? 'Weather'}</h3>
        {data.stale && <span className="wx__stale">cached</span>}
      </div>

      {data.alerts?.map((a) => (
        <div key={a.event} className="wx__alert" title={a.headline}>
          ⚠️ {a.event}
        </div>
      ))}

      {c && (
        <div className="wx__now">
          <div className="wx__icon">{weatherIcon(c.short, c.is_daytime)}</div>
          <div className="wx__temp">
            {c.temp}
            <span className="wx__deg">°{unit}</span>
          </div>
          <div className="wx__meta">
            <div className="wx__cond">{c.short}</div>
            <div className="wx__pills">
              {c.feels_like !== null && c.feels_like !== c.temp && (
                <span>Feels {c.feels_like}°</span>
              )}
              {c.pop > 0 && <span>{c.pop}% rain</span>}
              {c.humidity !== null && <span>{c.humidity}% humidity</span>}
              {c.wind && <span>{c.wind}</span>}
            </div>
          </div>
        </div>
      )}

      <div className="wx__days">
        {(data.days ?? []).slice(0, dayCount).map((d, i) => (
          <div key={d.date} className="wx__day">
            <div className="wx__dayname">{i === 0 ? 'Today' : dayLabel(d.date)}</div>
            <div className="wx__dayicon">{weatherIcon(d.short)}</div>
            <div className="wx__dayhigh">{d.high ?? '–'}°</div>
            <div className="wx__daylow">{d.low ?? '–'}°</div>
            {d.pop > 20 && <div className="wx__daypop">{d.pop}%</div>}
          </div>
        ))}
      </div>
    </>
  )
}

/** Dates arrive as plain YYYY-MM-DD; parsing them with new Date() would treat
 *  them as UTC midnight and shift the weekday for anyone west of Greenwich. */
function dayLabel(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  return format(new Date(y, m - 1, d), 'EEE')
}

// ------------------------------- Countdown -----------------------------------

function Countdown({ config, onConfigChange }: WidgetProps) {
  const label = str(config, 'label', 'Set a date')
  const emoji = str(config, 'emoji')
  const target = str(config, 'date')
  // No global widget-config editor exists, so the widget owns its own -- same
  // pattern the note widget uses. Tap the card to edit, blur to save.
  const [editing, setEditing] = useState(!target)

  const days = (() => {
    if (!target) return null
    const [y, m, d] = target.split('-').map(Number)
    if (!y || !m || !d) return null
    const then = new Date(y, m - 1, d)
    const today = startOfToday()
    return Math.round((then.getTime() - today.getTime()) / 86_400_000)
  })()

  if (editing) {
    return (
      <div className="countdown countdown--editing">
        <label className="field">
          <span>Counting down to</span>
          <input
            value={label === 'Set a date' ? '' : label}
            placeholder="Disney"
            onChange={(e) => onConfigChange({ ...config, label: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Date</span>
          <input
            type="date"
            value={target}
            onChange={(e) => onConfigChange({ ...config, date: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Emoji (optional)</span>
          <input
            value={emoji}
            placeholder="🎢"
            maxLength={4}
            onChange={(e) => onConfigChange({ ...config, emoji: e.target.value })}
          />
        </label>
        <button className="btn btn--primary" onClick={() => setEditing(false)} disabled={!target}>
          Done
        </button>
      </div>
    )
  }

  return (
    <button className="countdown" onClick={() => setEditing(true)}>
      {emoji && <div className="countdown__emoji">{emoji}</div>}
      {days === null ? (
        <div className="countdown__none">Tap to set a date</div>
      ) : (
        <>
          <div className="countdown__number">{days === 0 ? 'Today' : Math.abs(days)}</div>
          {days !== 0 && (
            <div className="countdown__unit">
              {Math.abs(days) === 1 ? 'day' : 'days'} {days > 0 ? 'to go' : 'ago'}
            </div>
          )}
        </>
      )}
      <div className="countdown__label">{label}</div>
    </button>
  )
}

// -------------------------------- registry -----------------------------------

export const WIDGETS: Record<string, WidgetDef> = {
  upcoming_events: { component: UpcomingEvents, label: 'Upcoming events' },
  today_agenda: { component: TodayAgenda, label: 'Today by person' },
  clock: { component: Clock, label: 'Clock and date' },
  mini_month: { component: MiniMonth, label: 'Month at a glance' },
  weather: { component: Weather, label: 'Weather' },
  list: { component: ListWidget, label: 'Shared list' },
  countdown: { component: Countdown, label: 'Countdown' },
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
