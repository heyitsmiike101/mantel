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
  server: {
    version: string
    google_configured: boolean
    sync_enabled: boolean
    sync_interval_seconds: number
  }
}
