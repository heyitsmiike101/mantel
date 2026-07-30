export interface User {
  id: number
  name: string
  color: string
  avatar_emoji: string | null
  sort_order: number
}

export interface CalendarInfo {
  id: number
  name: string
  is_local: boolean
  google_calendar_id: string | null
  linked_account_id: number | null
  account_email: string | null
  claimed_by_user_id: number | null
  color: string
  sync_enabled: boolean
  access_role: string
  writable: boolean
  last_synced_at: string | null
  sync_error: string | null
}

export interface CalendarEvent {
  id: number
  calendar_id: number
  calendar_name: string
  color: string
  user_id: number | null
  title: string
  description: string | null
  location: string | null
  start_at: string
  end_at: string
  all_day: boolean
  timezone: string | null
  recurring: boolean
  recurrence_rule: string | null
  recurrence_text: string | null
  origin: 'local' | 'google'
  sync_state: string
  editable: boolean
}

export interface EventInput {
  calendar_id: number
  title: string
  description?: string | null
  location?: string | null
  start_at: string
  end_at: string
  all_day?: boolean
  recurrence_rule?: string | null
}

export interface Photo {
  id: number
  original_name: string | null
  width: number
  height: number
  size_bytes: number
  sort_order: number
  url: string
}

export interface WeatherDay {
  date: string
  high: number | null
  low: number | null
  pop: number
  short: string | null
}

export interface Weather {
  available: boolean
  stale: boolean
  reason?: string
  provider?: string
  units?: string
  place?: string | null
  current?: {
    temp: number | null
    feels_like: number | null
    humidity: number | null
    short: string | null
    pop: number
    wind: string | null
    wind_direction: string | null
    is_daytime: boolean
  } | null
  days?: WeatherDay[]
  hourly?: { time: string; temp: number | null; pop: number; short: string | null }[]
  alerts?: { event: string; severity: string; headline: string }[]
}

export interface PlaceMatch {
  name: string
  admin1: string | null
  country: string | null
  latitude: number
  longitude: number
  label: string
}

export interface AppSettings {
  first_day_of_week: number
  time_format_24h: boolean
  home_timezone: string
  default_view: string
  kiosk_default_route: string
  display_scale: 'normal' | 'large' | 'wall'
  day_start_hour: number
  day_end_hour: number
  screensaver_enabled: boolean
  screensaver_delay_minutes: number
  screensaver_mode: 'auto' | 'photos' | 'clock' | 'off'
  screensaver_shuffle: boolean
  screensaver_seconds_per_photo: number
  sleep_enabled: boolean
  sleep_start_hour: number
  sleep_end_hour: number
  burn_in_shift: boolean
  weather_enabled: boolean
  weather_lat: number | null
  weather_lon: number | null
  weather_place: string
  weather_provider: 'auto' | 'nws' | 'open-meteo'
  weather_units: 'imperial' | 'metric'
  server: {
    version: string
    google_configured: boolean
    sync_enabled: boolean
    sync_interval_seconds: number
  }
}
