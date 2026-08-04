import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import type { AppSettings, CalendarInfo, User } from '../../api/types'
import { ApiTab } from './ApiTab'
import { GoogleTab } from './GoogleTab'
import { ScreenTab } from './ScreenTab'
import { SharingTab } from './SharingTab'
import { WeatherTab } from './WeatherTab'
import { PALETTE } from './palette'

const TABS = [
  'people',
  'google',
  'calendars',
  'display',
  'screen',
  'weather',
  'sharing',
  'api',
] as const

type Tab = (typeof TABS)[number]

const TAB_LABELS: Record<Tab, string> = {
  people: 'Family',
  google: 'Google',
  calendars: 'Calendars',
  display: 'Display',
  screen: 'Screen',
  weather: 'Weather',
  sharing: 'Sharing',
  api: 'API',
}

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>(() => {
    const requested = new URLSearchParams(window.location.search).get('tab')
    return TABS.includes(requested as Tab) ? (requested as Tab) : 'people'
  })
  return (
    <div className="settings">
      <div className="settings__tabs">
        {TABS.map((t) => (
          <button
            key={t}
            className="settings__tab"
            aria-current={tab === t ? 'page' : undefined}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      <div className="settings__body">
        {tab === 'people' && <PeopleTab />}
        {tab === 'google' && <GoogleTab />}
        {tab === 'calendars' && <CalendarsTab />}
        {tab === 'display' && <DisplayTab />}
        {tab === 'screen' && <ScreenTab />}
        {tab === 'weather' && <WeatherTab />}
        {tab === 'sharing' && <SharingTab />}
        {tab === 'api' && <ApiTab />}
      </div>
    </div>
  )
}

function PeopleTab() {
  const { data: users = [] } = useUsers()
  const [name, setName] = useState('')

  const createUser = useEntityMutation(
    (body: { name: string }) => api.post<User>('/users', body),
    ['users'],
  )
  const updateUser = useEntityMutation(
    ({ id, ...patch }: { id: number } & Partial<User>) => api.patch<User>(`/users/${id}`, patch),
    ['users', 'events', 'calendars'],
  )
  const deleteUser = useEntityMutation(
    (id: number) => api.del<void>(`/users/${id}`),
    ['users', 'calendars', 'events'],
  )

  return (
    <section className="panel">
      <h2>Family members</h2>
      <p className="hint">Each person gets a color. Their calendars use it everywhere.</p>

      {users.map((u) => (
        <div key={u.id} className="row">
          <span className="swatch" style={{ background: u.color }} />
          <input
            className="row__name"
            value={u.name}
            onChange={(e) => updateUser.mutate({ id: u.id, name: e.target.value })}
          />
          <div className="palette">
            {PALETTE.map((c) => (
              <button
                key={c}
                className="palette__dot"
                data-selected={c === u.color}
                style={{ background: c }}
                aria-label={`Set ${u.name}'s color`}
                onClick={() => updateUser.mutate({ id: u.id, color: c })}
              />
            ))}
          </div>
          <button className="btn btn--danger" onClick={() => deleteUser.mutate(u.id)}>
            Remove
          </button>
        </div>
      ))}

      <div className="row">
        <input
          className="row__name"
          placeholder="Add a family member"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && name.trim()) {
              createUser.mutate({ name: name.trim() })
              setName('')
            }
          }}
        />
        <button
          className="btn btn--primary"
          onClick={() => {
            if (!name.trim()) return
            createUser.mutate({ name: name.trim() })
            setName('')
          }}
        >
          Add
        </button>
      </div>
    </section>
  )
}

function CalendarsTab() {
  const { data: calendars = [] } = useCalendars()
  const { data: users = [] } = useUsers()
  const [name, setName] = useState('')
  const [checking, setChecking] = useState(false)
  const [found, setFound] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // A calendar created or shared in Google after the account was linked only
  // shows up once we re-read the list. Syncing does this on its own now; this is
  // the "I just made one, show me" button.
  const checkForNew = async () => {
    setChecking(true)
    setFound(null)
    try {
      const r = await api.post<{ new_calendars: number; total_calendars: number }>(
        '/sync/calendars',
      )
      await queryClient.invalidateQueries({ queryKey: ['calendars'] })
      setFound(
        r.new_calendars === 0
          ? `No new calendars — ${r.total_calendars} already listed.`
          : `Found ${r.new_calendars} new calendar${r.new_calendars === 1 ? '' : 's'}. ` +
            'Switch Syncing on for the ones you want.',
      )
    } catch (e) {
      setFound(e instanceof Error ? e.message : 'Could not reach Google.')
    } finally {
      setChecking(false)
    }
  }

  const updateCal = useEntityMutation(
    ({ id, ...patch }: { id: number } & Partial<CalendarInfo>) =>
      api.patch<CalendarInfo>(`/calendars/${id}`, patch),
    ['calendars', 'events'],
  )
  const createCal = useEntityMutation(
    (body: { name: string }) => api.post<CalendarInfo>('/calendars', body),
    ['calendars'],
  )
  const deleteCal = useEntityMutation(
    (id: number) => api.del<void>(`/calendars/${id}`),
    ['calendars', 'events'],
  )

  return (
    <section className="panel">
      <h2>Calendars</h2>
      <p className="hint">
        Claiming a calendar assigns it to a person and gives its events that person's color.
      </p>

      <div className="row">
        <div className="row__name row__name--static">
          Added a calendar in Google?
          <div className="hint">
            Syncing checks for new ones automatically — this is the impatient button.
          </div>
        </div>
        <button className="btn" onClick={checkForNew} disabled={checking}>
          {checking ? 'Checking…' : 'Check for new calendars'}
        </button>
      </div>
      {found && <p className="banner">{found}</p>}

      {calendars.map((c) => (
        <div key={c.id} className="row">
          <span className="swatch" style={{ background: c.color }} />
          <div className="row__name row__name--static">
            <div>{c.name}</div>
            <div className="hint">
              {c.is_local ? 'Local calendar' : `Google · ${c.account_email ?? ''}`}
              {!c.writable && ' · read-only'}
            </div>
          </div>
          <select
            value={c.claimed_by_user_id ?? ''}
            onChange={(e) =>
              updateCal.mutate({
                id: c.id,
                claimed_by_user_id: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">Unclaimed</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          {c.is_local && (
            <button className="btn btn--danger" onClick={() => deleteCal.mutate(c.id)}>
              Delete
            </button>
          )}
        </div>
      ))}

      <div className="row">
        <input
          className="row__name"
          placeholder="New local calendar (e.g. Chores)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          className="btn btn--primary"
          onClick={() => {
            if (!name.trim()) return
            createCal.mutate({ name: name.trim() })
            setName('')
          }}
        >
          Add
        </button>
      </div>
    </section>
  )
}

function DisplayTab() {
  const { data: settings } = useSettings()
  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings'],
  )
  if (!settings) return null

  return (
    <section className="panel">
      <h2>Display</h2>
      <p className="hint">These apply to every screen in the house.</p>

      <div className="row">
        <div className="row__name row__name--static">Text size</div>
        {(['normal', 'large', 'wall'] as const).map((s) => (
          <button
            key={s}
            className="btn"
            aria-current={settings.display_scale === s ? 'page' : undefined}
            onClick={() => save.mutate({ display_scale: s })}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="row__name row__name--static">Week starts on</div>
        {(
          [
            [0, 'Sunday'],
            [1, 'Monday'],
          ] as const
        ).map(([v, label]) => (
          <button
            key={v}
            className="btn"
            aria-current={settings.first_day_of_week === v ? 'page' : undefined}
            onClick={() => save.mutate({ first_day_of_week: v })}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="row__name row__name--static">Clock</div>
        {(
          [
            [false, '12-hour'],
            [true, '24-hour'],
          ] as const
        ).map(([v, label]) => (
          <button
            key={label}
            className="btn"
            aria-current={settings.time_format_24h === v ? 'page' : undefined}
            onClick={() => save.mutate({ time_format_24h: v })}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="row__name row__name--static">Day starts / ends</div>
        <select
          value={settings.day_start_hour}
          onChange={(e) => save.mutate({ day_start_hour: Number(e.target.value) })}
        >
          {hours().map((h) => (
            <option key={h} value={h}>
              {h}:00
            </option>
          ))}
        </select>
        <select
          value={settings.day_end_hour}
          onChange={(e) => save.mutate({ day_end_hour: Number(e.target.value) })}
        >
          {hours().map((h) => (
            <option key={h} value={h}>
              {h}:00
            </option>
          ))}
        </select>
      </div>

      <h3 className="settings__h3">Shortcut button</h3>
      <p className="hint">
        Adds a button to the top of every page, linking anywhere you like — another dashboard,
        a camera page. Leave the link blank to remove the bar entirely.
      </p>

      <div className="row">
        <div className="row__name row__name--static">Button text</div>
        <input
          className="row__name"
          placeholder="wall"
          defaultValue={settings.bookmark_label}
          onBlur={(e) => save.mutate({ bookmark_label: e.target.value.trim() })}
        />
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Link
          <div className="hint">Must start with http:// or https://.</div>
        </div>
        <input
          className="row__name"
          placeholder="http://dash.lan/?view=wall"
          defaultValue={settings.bookmark_url}
          onBlur={(e) => save.mutate({ bookmark_url: e.target.value.trim() })}
        />
      </div>

      <p className="hint">
        Server version {settings.server.version} ·{' '}
        {settings.server.google_configured
          ? 'Google sync configured'
          : 'Google sync not configured'}
      </p>
    </section>
  )
}

function hours(): number[] {
  return Array.from({ length: 25 }, (_, i) => i)
}
