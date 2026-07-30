import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation, useSettings } from '../../api/hooks'
import type { AppSettings } from '../../api/types'

interface FeedToken {
  token: string
  all_calendars_url: string
  hint: string
}

export function SharingTab() {
  const { data: settings } = useSettings()
  const { data: calendars = [] } = useCalendars()
  const { data: feed } = useQuery({
    queryKey: ['feed-token'],
    queryFn: () => api.get<FeedToken>('/feeds/token'),
  })

  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings'],
  )

  const [copied, setCopied] = useState<string | null>(null)
  const [haResult, setHaResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  if (!settings || !feed) return null

  const copy = async (url: string, label: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(label)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      setCopied('Copy failed — select the link and copy it manually.')
    }
  }

  const base = feed.all_calendars_url.split('/api/feeds/')[0]
  const feedUrl = (path: string) => `${base}/api/feeds/${path}?token=${feed.token}`

  const testHa = async () => {
    setTesting(true)
    setHaResult(null)
    try {
      const r = await api.post<{ ok: boolean; message: string }>('/settings/test-home-assistant')
      setHaResult(r.message)
    } catch (e) {
      setHaResult(e instanceof Error ? e.message : 'Test failed.')
    } finally {
      setTesting(false)
    }
  }

  return (
    <section className="panel">
      <h2>Subscribe on your phone</h2>
      <p className="hint">
        A read-only link anyone in the family can add to Apple Calendar, Google Calendar or
        Outlook. Changes made here show up there automatically. Treat the link like a password —
        anyone who has it can read the family's schedule.
      </p>

      <div className="row">
        <div className="row__name row__name--static">
          Everything
          <div className="hint feedurl">{feedUrl('all.ics')}</div>
        </div>
        <button className="btn btn--primary" onClick={() => copy(feedUrl('all.ics'), 'all')}>
          {copied === 'all' ? 'Copied' : 'Copy link'}
        </button>
      </div>

      {calendars.map((c) => (
        <div key={c.id} className="row">
          <div className="row__name row__name--static">
            <span className="swatch" style={{ background: c.color, marginRight: 8 }} />
            {c.name}
          </div>
          <button
            className="btn"
            onClick={() => copy(feedUrl(`${c.id}.ics`), String(c.id))}
          >
            {copied === String(c.id) ? 'Copied' : 'Copy link'}
          </button>
        </div>
      ))}

      <p className="hint">
        <strong>On an iPhone:</strong> Settings → Apps → Calendar → Accounts → Add Account →
        Other → Add Subscribed Calendar, then paste the link.
      </p>

      <h2 style={{ marginTop: 24 }}>Home Assistant</h2>
      <p className="hint">
        Optional. Add the family calendar to Home Assistant with its built-in{' '}
        <strong>Remote Calendar</strong> integration, using the link above. Because Remote
        Calendar only refreshes once a day, fill in the fields below and this app will tell
        Home Assistant to refresh the moment anything changes.
      </p>

      <div className="row">
        <div className="row__name row__name--static">Home Assistant URL</div>
        <input
          className="row__name"
          placeholder="http://homeassistant.local:8123"
          defaultValue={settings.ha_base_url}
          onBlur={(e) => save.mutate({ ha_base_url: e.target.value.trim() })}
        />
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Long-lived access token
          <div className="hint">Home Assistant → your profile → Security → Create token</div>
        </div>
        <input
          className="row__name"
          type="password"
          placeholder={settings.ha_token ? '••••••••' : 'Paste the token'}
          onBlur={(e) => e.target.value && save.mutate({ ha_token: e.target.value.trim() })}
        />
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Calendar entity
          <div className="hint">The entity Remote Calendar created, e.g. calendar.family</div>
        </div>
        <input
          className="row__name"
          defaultValue={settings.ha_entity_id}
          onBlur={(e) => save.mutate({ ha_entity_id: e.target.value.trim() })}
        />
        <button className="btn" onClick={testHa} disabled={testing}>
          {testing ? 'Testing…' : 'Test'}
        </button>
      </div>

      {haResult && <p className="banner banner--warn">{haResult}</p>}

      <p className="hint">
        Remember to turn off polling for that entity in Home Assistant (its integration page →
        the entity → gear → Enable polling for updates → off), or it will keep its own
        once-a-day schedule as well.
      </p>
    </section>
  )
}
