import { addDays, format, isSameDay, isSameMonth } from 'date-fns'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { useEntityMutation, useEvents, useSettings, useUsers, useWeather } from '../../api/hooks'
import type { SharedList } from '../../api/types'
import type { CalendarEvent, Weather as WeatherData } from '../../api/types'
import { rangeFor } from '../calendar/dateRange'
import { overlapsDay } from '../calendar/overlap'

export interface WidgetProps {
  widgetId?: number
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

function ClockDisplay({ showSeconds = false, compact = false }: { showSeconds?: boolean; compact?: boolean }) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), showSeconds ? 1000 : 20_000)
    return () => clearInterval(timer)
  }, [showSeconds])

  return (
    <div className={compact ? 'clock clock--compact' : 'clock'}>
      <div className="clock__time">{format(now, showSeconds ? 'h:mm:ss' : 'h:mm')}</div>
      <div className="clock__date">{format(now, 'EEEE, MMMM d')}</div>
    </div>
  )
}

function Clock({ config }: WidgetProps) {
  return <ClockDisplay showSeconds={config.show_seconds === true} />
}

export function DashboardClock() {
  return <ClockDisplay compact />
}

// ------------------------------- Mini month ----------------------------------

function MiniMonth({ onNewEvent }: WidgetProps) {
  const navigate = useNavigate()
  const { data: settings } = useSettings()
  const today = new Date()
  const weekStartsOn = (settings?.first_day_of_week === 1 ? 1 : 0) as 0 | 1
  const { days, start, end } = rangeFor('month', today, weekStartsOn)
  const { data: events = [] } = useEvents(start, end)
  const labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const ordered = weekStartsOn === 1 ? [...labels.slice(1), labels[0]] : labels

  return (
    <>
      <div className="widget__head">
        <h3>{format(today, 'MMMM yyyy')}</h3>
        <button className="iconbtn iconbtn--primary" aria-label="Add event" onClick={() => onNewEvent(nextHour())}>
          +
        </button>
      </div>
      <div className="minimonth">
        {ordered.map((label) => (
          <div key={label} className="minimonth__label">
            {label}
          </div>
        ))}
        {days.map((day) => {
          const dayEvents = events.filter((event) => overlapsDay(event, day))
          return (
            <button
              key={format(day, 'yyyy-MM-dd')}
              className="minimonth__day"
              data-today={isSameDay(day, today)}
              data-outside={!isSameMonth(day, today)}
              aria-label={`${format(day, 'EEEE, MMMM d')}, ${dayEvents.length} ${dayEvents.length === 1 ? 'event' : 'events'}`}
              onClick={() => navigate(`/calendar/today?date=${format(day, 'yyyy-MM-dd')}`)}
            >
              <span className="minimonth__number" aria-hidden>{format(day, 'd')}</span>
              {dayEvents.slice(0, 2).map((event) => (
                <span key={event.id} className="minimonth__event" style={{ background: event.color }} title={event.title} aria-hidden>
                  {event.title}
                </span>
              ))}
              {dayEvents.length > 2 && (
                <span className="minimonth__more" aria-hidden>+{dayEvents.length - 2} more</span>
              )}
            </button>
          )
        })}
      </div>
    </>
  )
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const

type Weekday = (typeof WEEKDAYS)[number]
type ChecklistItem = { id: string; text: string; checked: boolean }
type WeeklyChecklist = Record<Weekday, ChecklistItem[]>

function readChecklist(value: unknown): WeeklyChecklist {
  const source = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  return Object.fromEntries(WEEKDAYS.map((day) => [
    day,
    Array.isArray(source[day])
      ? source[day].filter((item): item is ChecklistItem =>
          item !== null && typeof item === 'object' &&
          typeof item.id === 'string' && typeof item.text === 'string' &&
          typeof item.checked === 'boolean')
      : [],
  ])) as WeeklyChecklist
}

export function readMealHistory(config: Record<string, unknown>): string[] {
  const checklist = readChecklist(config.checklist)
  const saved = Array.isArray(config.meal_history) ? config.meal_history : []
  const names = [...saved, ...WEEKDAYS.flatMap((day) => checklist[day].map((item) => item.text))]
  const seen = new Set<string>()
  return names.filter((value): value is string => {
    if (typeof value !== 'string' || !value.trim() || seen.has(value.trim().toLowerCase())) return false
    seen.add(value.trim().toLowerCase())
    return true
  }).map((value) => value.trim()).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
}

function ChecklistDay({ day, items, pending, onAdd, onRemove }: {
  day: Weekday
  items: ChecklistItem[]
  pending: boolean
  onAdd: (day: Weekday, text: string) => Promise<unknown>
  onRemove: (day: Weekday, id: string) => void
}) {
  const [draft, setDraft] = useState('')
  const submit = async () => {
    if (!draft.trim() || pending) return
    try {
      await onAdd(day, draft.trim())
      setDraft('')
    } catch {
      return
    }
  }

  return (
    <section className="weekcheck__day">
      <h4>{day}</h4>
      <ul className="weekcheck__items">
        {items.map((item) => (
          <li key={item.id} className="weekcheck__item">
            <button
              className="weekcheck__toggle"
              disabled={pending}
              aria-label={`Complete ${item.text} on ${day}`}
              onClick={() => onRemove(day, item.id)}
            />
            <span className="weekcheck__text">{item.text}</span>
          </li>
        ))}
      </ul>
      <div className="weekcheck__add">
        <input
          aria-label={`Add item to ${day}`}
          placeholder="Add a meal or task"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void submit() }}
        />
        <button aria-label={`Add to ${day}`} disabled={pending} onClick={() => void submit()}>+</button>
      </div>
    </section>
  )
}

type ChecklistEdit = {
  operation: 'add' | 'remove'
  day: Weekday
  id: string
  text?: string
}

export function newChecklistItemId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

export function PreviousMealsDialog({ meals, selected, day, pending, error, added, onSelect, onDayChange, onAdd, onClose }: {
  meals: string[]
  selected: string
  day: Weekday
  pending: boolean
  error: boolean
  added: string
  onSelect: (meal: string) => void
  onDayChange: (day: Weekday) => void
  onAdd: () => void
  onClose: () => void
}) {
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="previous-meals-title">
      <div className="modal__card weekcheck__dialog">
        <h2 className="modal__title" id="previous-meals-title">Add previous meal</h2>
        {meals.length === 0 ? (
          <p className="modal__note">Meals you add to the checklist will appear here.</p>
        ) : (
          <div className="weekcheck__history" role="group" aria-label="Previous meals">
            {meals.map((meal) => (
              <button
                key={meal}
                className="weekcheck__history-item"
                aria-pressed={selected === meal}
                onClick={() => onSelect(meal)}
              >
                {meal}
              </button>
            ))}
          </div>
        )}
        <label className="field">
          Day
          <select value={day} onChange={(e) => onDayChange(e.target.value as Weekday)}>
            {WEEKDAYS.map((weekday) => <option key={weekday} value={weekday}>{weekday}</option>)}
          </select>
        </label>
        {error && <p role="alert" className="modal__error">Could not add meal. Please try again.</p>}
        {added && !error && <p role="status" className="modal__note">{added}</p>}
        <div className="modal__actions">
          <button className="btn" disabled={!selected || pending} onClick={onAdd}>Add to {day}</button>
          <div className="modal__spacer" />
          <button className="btn" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

function SevenDayChecklist({ widgetId, config }: WidgetProps) {
  const queryClient = useQueryClient()
  const [showPrevious, setShowPrevious] = useState(false)
  const [selectedMeal, setSelectedMeal] = useState('')
  const [selectedDay, setSelectedDay] = useState<Weekday>('Monday')
  const [lastAdded, setLastAdded] = useState('')
  const checklist = readChecklist(config.checklist)
  const meals = readMealHistory(config)
  const edit = useMutation({
    mutationFn: (change: ChecklistEdit) => {
      if (widgetId === undefined) throw new Error('Checklist widget is missing its ID')
      return api.post<{ id: number; config: Record<string, unknown> }>(`/dashboard/widgets/${widgetId}/checklist`, change)
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<{ id: number; config: Record<string, unknown> }[]>(['widgets'], (current) =>
        current?.map((widget) => widget.id === saved.id ? { ...widget, config: saved.config } : widget),
      )
    },
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: ['widgets'] }) },
  })

  return (
    <>
      <div className="widget__head">
        <h3>7 day checklist</h3>
        <button className="iconbtn" onClick={() => setShowPrevious(true)}>Add previous</button>
      </div>
      {edit.isPending && !showPrevious && <p role="status">Saving checklist…</p>}
      {edit.isError && !showPrevious && <p role="alert">Could not save checklist. Please try again.</p>}
      <div className="weekcheck">
        {WEEKDAYS.map((day) => (
          <ChecklistDay
            key={day}
            day={day}
            items={checklist[day]}
            pending={edit.isPending}
            onAdd={(selected, text) => edit.mutateAsync({
              operation: 'add', day: selected, id: newChecklistItemId(), text,
            })}
            onRemove={(selected, id) => edit.mutate({ operation: 'remove', day: selected, id })}
          />
        ))}
      </div>
      {showPrevious && createPortal(
        <PreviousMealsDialog
          meals={meals}
          selected={selectedMeal}
          day={selectedDay}
          pending={edit.isPending}
          error={edit.isError}
          added={lastAdded}
          onSelect={(meal) => { setSelectedMeal(meal); setLastAdded('') }}
          onDayChange={(day) => { setSelectedDay(day); setLastAdded('') }}
          onAdd={() => {
            if (!selectedMeal || edit.isPending) return
            setLastAdded('')
            void edit.mutateAsync({
              operation: 'add', day: selectedDay, id: newChecklistItemId(), text: selectedMeal,
            }).then(() => setLastAdded(`${selectedMeal} added to ${selectedDay}.`), () => {})
          }}
          onClose={() => { setShowPrevious(false); setLastAdded('') }}
        />,
        document.body,
      )}
    </>
  )
}

// ---------------------------------- Note -------------------------------------

export function ExtendedForecastDialog({ onClose }: { onClose: () => void }) {
  const doneRef = useRef<HTMLButtonElement>(null)
  const forecastRef = useRef<HTMLDivElement>(null)
  const { data: weather, isLoading, isError } = useQuery({
    queryKey: ['weather', 'extended'],
    queryFn: () => api.get<WeatherData>('/weather/extended'),
    staleTime: 10 * 60_000,
  })
  const seen = new Set<string>()
  const days = (weather?.days ?? []).filter((day) => {
    if (seen.has(day.date)) return false
    seen.add(day.date)
    return true
  }).slice(0, 10)
  const unit = weather?.units === 'metric' ? 'C' : 'F'

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    doneRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'Tab') {
        event.preventDefault()
        const target = document.activeElement === doneRef.current
          ? forecastRef.current ?? doneRef.current
          : doneRef.current
        target?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previousFocus?.focus()
    }
  }, [onClose])

  return (
    <div className="modal" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="modal__card note__forecast-dialog" role="dialog" aria-modal="true" aria-labelledby="extended-forecast-title" aria-describedby="extended-forecast-source">
        <h2 className="modal__title" id="extended-forecast-title">10-day forecast</h2>
        <p className="modal__note" id="extended-forecast-source">Open-Meteo forecast{weather?.place ? ` · ${weather.place}` : ''} · {unit === 'C' ? '°C' : '°F'}</p>
        {isLoading ? (
          <p className="modal__note" role="status">Loading forecast…</p>
        ) : isError ? (
          <p className="modal__error" role="alert">Could not load the forecast. Please try again later.</p>
        ) : !weather?.available ? (
          <p className="modal__note">{weather?.reason ?? 'Forecast unavailable.'}</p>
        ) : days.length === 0 ? (
          <p className="modal__note">No forecast days available.</p>
        ) : (
          <div ref={forecastRef} className="note__forecast-list" role="region" aria-label="Daily forecast" tabIndex={0}>
            <ol className="note__forecast-cards">
              {days.map((day) => {
                const [year, month, date] = day.date.split('-').map(Number)
                const localDate = new Date(year, month - 1, date)
                return (
                  <li className="wx__day note__forecast-card" key={day.date}>
                    <time dateTime={day.date} aria-label={format(localDate, 'EEEE, MMMM d, yyyy')}>
                      <span className="wx__dayname">{format(localDate, 'EEE')}</span>
                      <span className="note__forecast-date">{format(localDate, 'MMM d')}</span>
                    </time>
                    <span className="wx__dayicon" aria-hidden="true">{weatherIcon(day.short)}</span>
                    <div className="note__forecast-temps">
                      <span className="wx__dayhigh" aria-label={`High ${day.high ?? '–'}°${unit}`}>{day.high ?? '–'}°</span>
                      <span aria-hidden="true"> / </span>
                      <span className="wx__daylow" aria-label={`Low ${day.low ?? '–'}°${unit}`}>{day.low ?? '–'}°</span>
                    </div>
                    <span className="note__forecast-condition">{day.short ?? 'Conditions unavailable'}</span>
                    <span className="wx__daypop note__forecast-rain">{day.pop}% rain</span>
                  </li>
                )
              })}
            </ol>
          </div>
        )}
        <div className="modal__actions">
          <div className="modal__spacer" />
          <button ref={doneRef} type="button" className="btn" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  )
}

function Note({ config, onConfigChange }: WidgetProps) {
  const [text, setText] = useState(typeof config.text === 'string' ? config.text : '')
  const [showForecast, setShowForecast] = useState(false)
  const closeForecast = useCallback(() => setShowForecast(false), [])
  const { data: weather, isLoading } = useWeather()
  const unit = weather?.units === 'metric' ? 'C' : 'F'
  const forecast = (weather?.days ?? []).slice(0, 3)

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
      <button type="button" className="note__weather" aria-label="Weather — open 10-day forecast" aria-haspopup="dialog" onClick={() => setShowForecast(true)}>
        {isLoading ? (
          <span className="widget__empty">Loading weather…</span>
        ) : !weather?.available ? (
          <span className="widget__empty">{weather?.reason ?? 'Weather is unavailable.'}</span>
        ) : (
          <>
            <span className="note__weather-head">
              <span className="note__place" title={weather.place ?? undefined}>{weather.place ?? 'Weather'}</span>
              {weather.stale && <span className="wx__stale">cached</span>}
            </span>
            {weather.current && (
              <span className="note__current">
                <span className="note__icon" aria-hidden="true">{weatherIcon(weather.current.short, weather.current.is_daytime)}</span>
                <strong>{weather.current.temp ?? '–'}°{unit}</strong>
                <span className="note__condition">{weather.current.short ?? 'Current conditions'}</span>
              </span>
            )}
            {forecast.length > 0 && (
              <span className="note__forecast" aria-label="Forecast">
                {forecast.map((day, index) => (
                  <span className="note__forecast-day" key={day.date}>
                    <span>{index === 0 ? 'Today' : dayLabel(day.date)}</span>
                    <span aria-hidden="true">{weatherIcon(day.short)}</span>
                    <span>{day.high ?? '–'}° / {day.low ?? '–'}°</span>
                  </span>
                ))}
              </span>
            )}
            {weather.alerts?.slice(0, 1).map((alert) => (
              <span key={alert.event} className="wx__alert" title={alert.headline}>{alert.event}</span>
            ))}
            {!weather.current && forecast.length === 0 && <span className="widget__empty">Forecast unavailable.</span>}
          </>
        )}
      </button>
      {showForecast && createPortal(<ExtendedForecastDialog onClose={closeForecast} />, document.body)}
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
  seven_day_checklist: { component: SevenDayChecklist, label: '7 day checklist' },
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
