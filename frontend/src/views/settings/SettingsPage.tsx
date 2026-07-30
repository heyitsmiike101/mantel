import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import type { AppSettings, CalendarInfo, User } from '../../api/types'
import { AccountsTab } from './AccountsTab'
import { ScreenTab } from './ScreenTab'
import { SharingTab } from './SharingTab'
import { WeatherTab } from './WeatherTab'
import { PALETTE } from './palette'

type Tab = 'people' | 'accounts' | 'calendars' | 'display' | 'screen' | 'weather' | 'sharing'

const TAB_LABELS: Record<Tab, string> = {
  people: 'Family',
  accounts: 'Google',
  calendars: 'Calendars',
  display: 'Display',
  screen: 'Screen',
  weather: 'Weather',
  sharing: 'Sharing',
}

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>(
    () => (new URLSearchParams(window.location.search).get('tab') as Tab) || 'people',
  )
  return (
    <div className="settings">
      <div className="settings__tabs">
        {(['people', 'accounts', 'calendars', 'display', 'screen', 'weather', 'sharing'] as Tab[]).map((t) => (
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
        {tab === 'accounts' && <AccountsTab />}
        {tab === 'calendars' && <CalendarsTab />}
        {tab === 'display' && <DisplayTab />}
        {tab === 'screen' && <ScreenTab />}
        {tab === 'weather' && <WeatherTab />}
        {tab === 'sharing' && <SharingTab />}
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
