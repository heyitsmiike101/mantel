import { useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation, useSettings } from '../../api/hooks'
import type { AppSettings, PlaceMatch } from '../../api/types'

export function WeatherTab() {
  const { data: settings } = useSettings()
  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings', 'weather'],
  )

  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<PlaceMatch[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!settings) return null

  const search = async () => {
    if (query.trim().length < 2) return
    setSearching(true)
    setError(null)
    try {
      const results = await api.get<PlaceMatch[]>(
        `/weather/search?q=${encodeURIComponent(query.trim())}`,
      )
      setMatches(results)
      if (results.length === 0) setError('No places matched that search.')
    } catch {
      setError("Couldn't reach the place lookup. Check the server's internet access.")
    } finally {
      setSearching(false)
    }
  }

  const choose = (place: PlaceMatch) => {
    save.mutate({
      weather_lat: place.latitude,
      weather_lon: place.longitude,
      weather_place: place.label,
    })
    setMatches(null)
    setQuery('')
  }

  const configured = settings.weather_lat !== null && settings.weather_lon !== null

  return (
    <section className="panel">
      <h2>Weather</h2>
      <p className="hint">
        Powered by the National Weather Service in the United States and Open-Meteo elsewhere.
        Both are free and need no account, so there is no API key to set up.
      </p>

      <div className="row">
        <div className="row__name row__name--static">Show weather</div>
        <button
          className="btn"
          aria-current={settings.weather_enabled ? 'page' : undefined}
          onClick={() => save.mutate({ weather_enabled: !settings.weather_enabled })}
        >
          {settings.weather_enabled ? '☑ On' : '☐ Off'}
        </button>
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Location
          <div className="hint">
            {configured ? (settings.weather_place || 'Set') : 'Not set yet'}
          </div>
        </div>
        <input
          className="row__name"
          placeholder="Town, city or postcode"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void search()}
        />
        <button className="btn btn--primary" onClick={search} disabled={searching}>
          {searching ? 'Searching…' : 'Search'}
        </button>
      </div>

      {error && <p className="banner banner--warn">{error}</p>}

      {matches && matches.length > 0 && (
        <div className="placelist">
          {matches.map((m) => (
            <button
              key={`${m.latitude},${m.longitude}`}
              className="picker"
              onClick={() => choose(m)}
            >
              <span className="picker__name">{m.label}</span>
              <span className="picker__desc">
                {m.latitude.toFixed(2)}, {m.longitude.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="row">
        <div className="row__name row__name--static">Units</div>
        {(
          [
            ['imperial', 'Fahrenheit'],
            ['metric', 'Celsius'],
          ] as const
        ).map(([v, label]) => (
          <button
            key={v}
            className="btn"
            aria-current={settings.weather_units === v ? 'page' : undefined}
            onClick={() => save.mutate({ weather_units: v })}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Source
          <div className="hint">
            Automatic uses the National Weather Service inside the US, which adds
            watches and warnings.
          </div>
        </div>
        {(
          [
            ['auto', 'Automatic'],
            ['nws', 'Weather Service'],
            ['open-meteo', 'Open-Meteo'],
          ] as const
        ).map(([v, label]) => (
          <button
            key={v}
            className="btn"
            aria-current={settings.weather_provider === v ? 'page' : undefined}
            onClick={() => save.mutate({ weather_provider: v })}
          >
            {label}
          </button>
        ))}
      </div>

      <p className="hint">
        Add the <strong>Weather</strong> widget on the Dashboard to see it.
      </p>
    </section>
  )
}
