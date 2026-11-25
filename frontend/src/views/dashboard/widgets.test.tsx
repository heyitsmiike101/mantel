import { renderToStaticMarkup } from 'react-dom/server'
import { useQuery } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEvents, useSettings, useWeather } from '../../api/hooks'
import { api } from '../../api/client'
import { DashboardPage } from './DashboardPage'
import type { CalendarEvent, Weather } from '../../api/types'
import { rangeFor } from '../calendar/dateRange'
import { ExtendedForecastDialog, newChecklistItemId, PreviousMealsDialog, readMealHistory, WIDGETS } from './widgets'

const mutationState = vi.hoisted(() => ({ isError: false, isPending: false }))
const forecastState = vi.hoisted(() => ({ data: undefined as Weather | undefined, isLoading: false, isError: false }))

vi.mock('../../api/hooks', () => ({
  useEvents: vi.fn(),
  useSettings: vi.fn(),
  useWeather: vi.fn(),
  useEntityMutation: () => ({ mutate: vi.fn() }),
}))
vi.mock('@tanstack/react-query', async (importOriginal) => ({
  ...await importOriginal<typeof import('@tanstack/react-query')>(),
  useQuery: vi.fn((options: { queryKey: string[] }) => options.queryKey[0] === 'weather' ? forecastState : { data: [] }),
  useQueryClient: () => ({ setQueryData: vi.fn(), invalidateQueries: vi.fn() }),
  useMutation: () => ({ ...mutationState, mutate: vi.fn(), mutateAsync: vi.fn() }),
}))

const MiniMonth = WIDGETS.mini_month.component
const event = (id: number, title: string, start_at: string, end_at: string): CalendarEvent => ({
  id,
  title,
  start_at,
  end_at,
  color: '#3b82f6',
  all_day: false,
} as CalendarEvent)

function render(events: CalendarEvent[], weekStart: 0 | 1 = 0) {
  vi.mocked(useSettings).mockReturnValue({ data: { first_day_of_week: weekStart } } as ReturnType<typeof useSettings>)
  vi.mocked(useEvents).mockReturnValue({ data: events } as ReturnType<typeof useEvents>)
  return renderToStaticMarkup(
    <MemoryRouter>
      <MiniMonth config={{}} onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.useRealTimers()
  mutationState.isError = false
  mutationState.isPending = false
  forecastState.data = undefined
  forecastState.isLoading = false
  forecastState.isError = false
  vi.restoreAllMocks()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('7 day checklist', () => {
  it('generates item IDs without randomUUID on an HTTP LAN origin', () => {
    let next = 0
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(next++)
        return bytes
      },
    })
    expect(newChecklistItemId()).toBe('00'.repeat(16))
    expect(newChecklistItemId()).toBe('01'.repeat(16))
  })
  it('renders fixed weekdays and persisted checklist items regardless of the current date', () => {
    const Checklist = WIDGETS.seven_day_checklist.component
    const config = { checklist: { Monday: [{ id: 'one', text: 'Pasta', checked: true }], Sunday: [{ id: 'two', text: 'Soup', checked: false }] } }
    const renderChecklist = () => renderToStaticMarkup(
      <Checklist config={config} onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />,
    )
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15))
    const html = renderChecklist()
    expect(html.match(/class="weekcheck__day"/g)).toHaveLength(7)
    expect([...html.matchAll(/<h4>(.*?)<\/h4>/g)].map((match) => match[1])).toEqual([
      'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    ])
    expect(html).toContain('Pasta')
    expect(html).toContain('Soup')
    expect(html).toContain('aria-label="Complete Pasta on Monday"')
    expect(html).toContain('aria-label="Complete Soup on Sunday"')
    expect(html).not.toContain('weekcheck__remove')
    expect(html).not.toContain('data-checked=')
    expect(html).toContain('aria-label="Add item to Sunday"')
    expect(html).toContain('Add previous')
    vi.setSystemTime(new Date(2027, 2, 1))
    expect(renderChecklist()).toBe(html)
  })

  it('shows a save failure without displaying an unsaved item as persisted', () => {
    mutationState.isError = true
    const Checklist = WIDGETS.seven_day_checklist.component
    const html = renderToStaticMarkup(
      <Checklist widgetId={1} config={{ checklist: { Monday: [{ id: 'one', text: 'Pasta', checked: false }] } }}
        onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />,
    )
    expect(html).toContain('role="alert"')
    expect(html).toContain('Could not save checklist. Please try again.')
    expect(html).toContain('Pasta')
    expect(html).not.toContain('Soup')
  })
})

describe('previous meals', () => {
  it('shows saved and current meals alphabetically without duplicate names', () => {
    expect(readMealHistory({
      meal_history: ['Pasta', 'Soup', ' pasta ', '', 'apple pie'],
      checklist: { Monday: [{ id: 'one', text: 'SOUP', checked: false }], Tuesday: [{ id: 'two', text: 'Curry', checked: false }] },
    })).toEqual(['apple pie', 'Curry', 'Pasta', 'Soup'])
  })

  it('offers meal selection, all seven days and a done action in a dialog', () => {
    const html = renderToStaticMarkup(
      <PreviousMealsDialog
        meals={['Pasta', 'Soup']}
        selected="Soup"
        day="Friday"
        pending={false}
        error={false}
        added="Soup added to Friday."
        onSelect={() => {}}
        onDayChange={() => {}}
        onAdd={() => {}}
        onClose={() => {}}
      />,
    )
    expect(html).toContain('role="dialog"')
    expect(html).toContain('aria-label="Previous meals"')
    expect(html).toContain('aria-pressed="true">Soup')
    expect(html).toContain('value="Friday" selected=""')
    expect(html).toContain('Add to Friday')
    expect(html).toContain('Soup added to Friday.')
    expect(html).toContain('Done</button>')
  })
})

describe('family note weather', () => {
  const Note = WIDGETS.note.component
  const renderNote = () => renderToStaticMarkup(
    <Note config={{ text: 'Dinner at six', other: 'keep' }} onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />,
  )

  it('keeps the saved note and shows compact local weather with available forecast days', () => {
    vi.mocked(useWeather).mockReturnValue({
      data: {
        available: true, stale: true, units: 'metric', place: 'Independence, Kentucky',
        current: { temp: 12, feels_like: 10, humidity: 50, short: 'Sunny', pop: 0, wind: null, wind_direction: null, is_daytime: true },
        days: [
          { date: '2026-11-18', high: 15, low: 3, pop: 0, short: 'Sunny' },
          { date: '2026-11-19', high: 16, low: 5, pop: 0, short: 'Cloudy' },
        ],
      },
      isLoading: false,
    } as ReturnType<typeof useWeather>)
    const html = renderNote()
    expect(html).toContain('Dinner at six</textarea>')
    expect(html).toContain('aria-label="Weather — open 10-day forecast"')
    expect(html).toContain('Independence, Kentucky')
    expect(html).toContain('12°C')
    expect(html).toContain('15° / 3°')
    expect(html).toContain('16° / 5°')
    expect(html.match(/class="note__forecast-day"/g)).toHaveLength(2)
    expect(html).toContain('aria-haspopup="dialog"')
    expect(html).toMatch(/<\/textarea><button[^>]*class="note__weather"/)
    expect(html).toContain('cached')
  })

  it('retains the note while weather loads or is unavailable', () => {
    vi.mocked(useWeather).mockReturnValue({ isLoading: true } as ReturnType<typeof useWeather>)
    expect(renderNote()).toContain('Loading weather…')
    vi.mocked(useWeather).mockReturnValue({ data: { available: false, stale: false, reason: 'Set a location first.' }, isLoading: false } as ReturnType<typeof useWeather>)
    const html = renderNote()
    expect(html).toContain('Dinner at six</textarea>')
    expect(html).toContain('Set a location first.')
  })
})

describe('extended forecast dialog', () => {
  const renderForecast = () => renderToStaticMarkup(<ExtendedForecastDialog onClose={() => {}} />)

  it('requests the extended endpoint only when the dialog is rendered', async () => {
    vi.mocked(useWeather).mockReturnValue({ data: { available: false, stale: false } } as ReturnType<typeof useWeather>)
    renderToStaticMarkup(<WIDGETS.note.component config={{ text: 'Dinner at six' }} onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />)
    expect(vi.mocked(useQuery)).not.toHaveBeenCalledWith(expect.objectContaining({ queryKey: ['weather', 'extended'] }))
    renderForecast()
    const options = vi.mocked(useQuery).mock.calls.find(([query]) =>
      (query as { queryKey: string[] }).queryKey[1] === 'extended')?.[0] as unknown as { queryFn: () => Promise<Weather> }
    const response = { available: true, stale: false } as Weather
    const get = vi.spyOn(api, 'get').mockResolvedValue(response)
    expect(await options.queryFn()).toBe(response)
    expect(get).toHaveBeenCalledWith('/weather/extended')
  })

  it('shows at most ten unique local calendar dates as Weather-style daily cards', () => {
    forecastState.data = {
      available: true, stale: false, units: 'metric', place: 'Independence, Kentucky',
      days: [
        { date: '2026-11-18', high: 0, low: -5, pop: 0, short: 'Cloudy' },
        { date: '2026-11-18', high: 99, low: 99, pop: 99, short: 'Sunny' },
        ...Array.from({ length: 10 }, (_, index) => ({
          date: `2026-11-${String(index + 19).padStart(2, '0')}`,
          high: index + 1, low: index - 4, pop: (index + 1) * 10, short: 'Cloudy',
        })),
      ],
    }
    const html = renderForecast()
    expect(html).toContain('role="dialog"')
    expect(html).toContain('Open-Meteo forecast · Independence, Kentucky · °C')
    expect(html).toContain('<ol class="note__forecast-cards">')
    expect(html.match(/<li class="wx__day note__forecast-card"/g)).toHaveLength(10)
    expect(html.match(/class="wx__dayicon" aria-hidden="true"/g)).toHaveLength(10)
    expect(html).not.toContain('note__forecast-icon')
    expect(html).toContain('dateTime="2026-11-18" aria-label="Wednesday, November 18, 2026"')
    expect(html).toContain('dateTime="2026-11-27" aria-label="Friday, November 27, 2026"')
    expect(html).not.toContain('Nov 28')
    expect(html).not.toContain('High 99')
    expect(html).toContain('Cloudy')
    expect(html).toContain('aria-label="High 0°C">0°')
    expect(html).toContain('aria-label="Low -5°C">-5°')
    expect(html).toContain('0% rain')
    expect(html).not.toContain('note__forecast-row')
  })

  it('reuses the original seven-day Weather widget icon class and condition icons', () => {
    const weather: Weather = {
      available: true, stale: false,
      days: ['Sunny', 'Cloudy', 'Rain', 'Snow', 'Fog', 'Thunderstorms', null].map((short, index) => ({
        date: `2026-11-${index + 18}`, high: 50, low: 40, pop: 0, short,
      })),
    }
    forecastState.data = weather
    vi.mocked(useWeather).mockReturnValue({ data: weather } as ReturnType<typeof useWeather>)
    const standalone = renderToStaticMarkup(
      <WIDGETS.weather.component config={{ days: 7 }} onConfigChange={() => {}} onOpenEvent={() => {}} onNewEvent={() => {}} />,
    )
    const icons = (html: string) => [...html.matchAll(/class="wx__dayicon"[^>]*>([^<]*)</g)].map((match) => match[1])
    expect(icons(standalone)).toHaveLength(7)
    expect(icons(renderForecast())).toEqual(icons(standalone))
  })

  it('keeps the forecast region focusable without scroll instructions and Done outside it', () => {
    forecastState.data = {
      available: true, stale: false,
      days: [
        { date: '2026-11-18', high: 50, low: 40, pop: 0, short: 'Sunny' },
        { date: '2026-11-19', high: 48, low: 39, pop: 80, short: 'Rain' },
      ],
    }
    const html = renderForecast()
    expect(html).toContain('role="region" aria-label="Daily forecast" tabindex="0"')
    expect(html).not.toContain('extended-forecast-hint')
    expect(html).not.toContain('Swipe or scroll')
    expect(html).not.toContain('Use ← → keys')
    expect(html).toMatch(/<\/ol><\/div>.*<div class="modal__actions">.*Done<\/button>/)
    expect(html).toContain('aria-label="High 50°F"')
    expect(html).toContain('80% rain')
  })

  it('keeps missing conditions and temperatures readable for one day', () => {
    forecastState.data = {
      available: true, stale: false, units: 'metric',
      days: [{ date: '2026-11-18', high: null, low: null, pop: 0, short: null }],
    }
    const html = renderForecast()
    expect(html).toContain('Conditions unavailable')
    expect(html).toContain('aria-label="High –°C">–°')
    expect(html).toContain('aria-label="Low –°C">–°')
    expect(html).not.toContain('extended-forecast-hint')
    expect(html).toContain('Done</button>')
  })

  it('shows loading, request failure, unavailable and empty states', () => {
    forecastState.isLoading = true
    expect(renderForecast()).toContain('Loading forecast…')
    forecastState.isLoading = false
    forecastState.isError = true
    expect(renderForecast()).toContain('Could not load the forecast.')
    forecastState.isError = false
    forecastState.data = { available: false, stale: false, reason: 'Set a location first.' }
    expect(renderForecast()).toContain('Set a location first.')
    forecastState.data = { available: true, stale: false, days: [] }
    expect(renderForecast()).toContain('No forecast days available.')
  })
})

describe('dashboard header', () => {
  it('shows the current time and date next to the heading even with no clock widget', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 14, 35))
    const html = renderToStaticMarkup(<MemoryRouter><DashboardPage /></MemoryRouter>)
    expect(html).toMatch(/<h1 class="dash__title">Dashboard<\/h1><div class="clock clock--compact">/)
    expect(html).toContain('class="clock__time">2:35</div>')
    expect(html).toContain('class="clock__date">Thursday, October 15</div>')
  })
})

describe('dashboard mini month', () => {
  it('uses the actual month range and the configured first weekday', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15))
    const html = render([], 1)
    const range = rangeFor('month', new Date(2026, 9, 15), 1)
    expect(html.match(/class="minimonth__day"/g)).toHaveLength(range.days.length)
    expect(html).toMatch(/class="minimonth__label">Mon<\/div>/)
    expect(vi.mocked(useEvents).mock.calls[0].slice(0, 2)).toEqual([range.start, range.end])
  })

  it('shows event titles and a count of hidden events inside a single day control', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15))
    const events = Array.from({ length: 4 }, (_, i) =>
      event(i + 1, `Appointment ${i + 1}`, '2026-10-15T15:00:00Z', '2026-10-15T16:00:00Z'),
    )
    const html = render(events)
    const day = html.match(/<button[^>]*aria-label="Thursday, October 15[^>]*>[\s\S]*?<\/button>/)?.[0]
    expect(day).toContain('Appointment 1')
    expect(day).toContain('Appointment 2')
    expect(day).not.toContain('Appointment 3</span>')
    expect(day).toContain('+2 more')
    expect(html).toContain('aria-label="Add event"')
  })
})
