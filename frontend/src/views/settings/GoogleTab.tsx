import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import type { AppSettings, CalendarInfo } from '../../api/types'

interface LinkedAccount {
  id: number
  user_id: number
  provider: string
  email: string
  status: string
  last_error: string | null
}

interface SyncStatus {
  google_configured: boolean
  sync_enabled: boolean
  interval_seconds: number
  accounts_needing_reauth: string[]
  pending_pushes: number
  calendars: {
    calendar_id: number
    name: string
    account_email: string | null
    sync_enabled: boolean
    last_synced_at: string | null
    sync_error: string | null
  }[]
}

export function GoogleTab() {
  const { data: settings } = useSettings()
  const { data: users = [] } = useUsers()
  const { data: calendars = [] } = useCalendars()
  const { data: accounts = [], refetch: refetchAccounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<LinkedAccount[]>('/accounts'),
  })
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatus>('/sync/status'),
    refetchInterval: 30_000,
  })

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSteps, setShowSteps] = useState(false)

  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings'],
  )
  const unlink = useEntityMutation(
    (id: number) => api.del<void>(`/accounts/${id}`),
    ['accounts', 'calendars', 'events', 'sync-status'],
  )
  const updateCal = useEntityMutation(
    ({ id, ...patch }: { id: number } & Partial<CalendarInfo>) =>
      api.patch<CalendarInfo>(`/calendars/${id}`, patch),
    ['calendars', 'events', 'sync-status'],
  )

  if (!settings) return null

  const configured = settings.server.google_configured
  // Defaulting to the address this browser is on is almost always the right
  // answer, and it is the value Google must be told about verbatim.
  const baseUrl = settings.public_base_url || window.location.origin
  const redirectUri = `${baseUrl.replace(/\/$/, '')}/api/accounts/google/callback`

  const connect = async (userId: number) => {
    setError(null)
    setBusy(true)
    try {
      const { url } = await api.get<{ url: string }>(
        `/accounts/google/auth-url?user_id=${userId}`,
      )
      window.location.href = url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the Google sign-in.')
      setBusy(false)
    }
  }

  const syncNow = async () => {
    setBusy(true)
    try {
      await api.post('/sync/run')
      await Promise.all([refetchStatus(), refetchAccounts()])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>Google Calendar</h2>
      <p className="hint">
        Optional, and worth it if your family already uses Google Calendar. Events sync both
        ways: what you add here shows up in Google within seconds, and what they add on their
        phones shows up here. You set this up <strong>once for the whole household</strong>,
        then each person connects their own account.
      </p>

      {!configured && (
        <p className="banner">
          Not set up yet. Follow the steps below — it takes about ten minutes and costs nothing.
        </p>
      )}

      <Steps open={showSteps} onToggle={() => setShowSteps((v) => !v)} redirectUri={redirectUri} />

      <h3 className="settings__h3">Your Google credentials</h3>

      <div className="row">
        <div className="row__name row__name--static">
          This app's address
          <div className="hint">
            How your family reaches this app. Must match what you gave Google in step 5.
          </div>
        </div>
        <input
          className="row__name"
          placeholder={window.location.origin}
          defaultValue={settings.public_base_url}
          onBlur={(e) =>
            save.mutate({ public_base_url: e.target.value.trim() || window.location.origin })
          }
        />
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Redirect URI
          <div className="hint">Paste this into Google exactly as shown.</div>
        </div>
        <CopyBox value={redirectUri} />
      </div>

      <div className="row">
        <div className="row__name row__name--static">Client ID</div>
        <input
          className="row__name"
          placeholder="1234567890-abc.apps.googleusercontent.com"
          defaultValue={settings.google_client_id}
          onBlur={(e) => save.mutate({ google_client_id: e.target.value.trim() })}
        />
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Client secret
          <div className="hint">
            {settings.server.google_client_secret_set
              ? 'Saved. Type a new one to replace it.'
              : 'From the same Google credentials screen.'}
          </div>
        </div>
        <input
          className="row__name"
          type="password"
          placeholder={
            settings.server.google_client_secret_set ? '••••••••••••' : 'GOCSPX-…'
          }
          onBlur={(e) =>
            e.target.value && save.mutate({ google_client_secret: e.target.value.trim() })
          }
        />
      </div>

      <h3 className="settings__h3">Connect an email</h3>
      <p className="hint">
        Each person connects their own Google account, and can add as many as they like — a
        personal Gmail and a work account both work. Connecting takes you to Google and back.
      </p>

      {users.length === 0 && (
        <p className="banner banner--warn">
          Add your family under Settings → Family first, so there is somebody to connect an
          account to.
        </p>
      )}

      {status && status.accounts_needing_reauth.length > 0 && (
        <p className="banner banner--warn">
          These need connecting again: {status.accounts_needing_reauth.join(', ')}
        </p>
      )}

      {users.map((u) => {
        const mine = accounts.filter((a) => a.user_id === u.id)
        return (
          <div key={u.id} className="row">
            <div className="row__name row__name--static row__name--inline">
              <span className="swatch" style={{ background: u.color }} />
              <div>
                <div>{u.name}</div>
                <div className="hint">
                  {mine.length === 0
                    ? 'No account connected'
                    : mine
                        .map(
                          (a) =>
                            `${a.email}${a.status === 'active' ? '' : ' (needs reconnecting)'}`,
                        )
                        .join(', ')}
                </div>
              </div>
            </div>
            {mine.map((a) => (
              <button key={a.id} className="btn btn--danger" onClick={() => unlink.mutate(a.id)}>
                Unlink {a.email.split('@')[0]}
              </button>
            ))}
            <button
              className="btn btn--primary"
              disabled={busy || !configured}
              onClick={() => connect(u.id)}
              title={configured ? undefined : 'Add your Google credentials above first'}
            >
              {mine.length === 0 ? 'Connect an email' : 'Add another'}
            </button>
          </div>
        )
      })}

      {error && <p className="banner banner--warn">{error}</p>}

      <h3 className="settings__h3">Calendars</h3>
      <p className="hint">
        Choose who each calendar belongs to and switch on the ones you want on the wall. Its
        events then show in that person's colour.
      </p>

      {calendars.filter((c) => !c.is_local).length === 0 && (
        <p className="hint">Nothing yet — connect an account above.</p>
      )}

      {calendars
        .filter((c) => !c.is_local)
        .map((c) => {
          const cal = status?.calendars.find((s) => s.calendar_id === c.id)
          return (
            <div key={c.id} className="row">
              <span className="swatch" style={{ background: c.color }} />
              <div className="row__name row__name--static">
                <div>{c.name}</div>
                <div className="hint">
                  {c.account_email}
                  {!c.writable && ' · read-only in Google'}
                  {cal?.last_synced_at && ` · synced ${timeAgo(cal.last_synced_at)}`}
                  {cal?.sync_error && ` · ${cal.sync_error.slice(0, 70)}`}
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
                <option value="">Nobody</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
              <button
                className="btn"
                aria-current={c.sync_enabled ? 'page' : undefined}
                onClick={() => updateCal.mutate({ id: c.id, sync_enabled: !c.sync_enabled })}
              >
                {c.sync_enabled ? 'Syncing' : 'Off'}
              </button>
            </div>
          )
        })}

      {status && (
        <div className="row">
          <div className="row__name row__name--static hint">
            Syncs every {Math.round(status.interval_seconds / 60)} min
            {status.pending_pushes > 0 && ` · ${status.pending_pushes} change(s) to send`}
          </div>
          <button className="btn" onClick={syncNow} disabled={busy || !configured}>
            {busy ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      )}
    </section>
  )
}

function Steps({
  open,
  onToggle,
  redirectUri,
}: {
  open: boolean
  onToggle: () => void
  redirectUri: string
}) {
  return (
    <div className="steps">
      <button className="steps__toggle" onClick={onToggle} aria-expanded={open}>
        {open ? '▾' : '▸'} How to get a Client ID and secret from Google
      </button>

      {open && (
        <ol className="steps__list">
          <li>
            Open <ExternalLink href="https://console.cloud.google.com/projectcreate" /> and
            create a project. Call it <code>Family Calendar</code>. It's free.
          </li>
          <li>
            Go to{' '}
            <ExternalLink
              href="https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"
              label="APIs &amp; Services → Library"
            />{' '}
            and press <strong>Enable</strong> on the Google Calendar API.
          </li>
          <li>
            Open{' '}
            <ExternalLink
              href="https://console.cloud.google.com/apis/credentials/consent"
              label="OAuth consent screen"
            />
            . Choose <strong>External</strong>, then fill in an app name and your own email
            twice. Skip the Scopes page.
            <div className="steps__note">
              Then press <strong>Publish App</strong>. If you leave it in Testing mode, Google
              expires the connection every 7 days and everyone has to reconnect weekly.
              Publishing an app that only you use needs no review.
            </div>
          </li>
          <li>
            Go to{' '}
            <ExternalLink
              href="https://console.cloud.google.com/apis/credentials"
              label="Credentials"
            />{' '}
            → <strong>Create Credentials</strong> → <strong>OAuth client ID</strong> →
            application type <strong>Web application</strong>.
          </li>
          <li>
            Under <strong>Authorized redirect URIs</strong>, press <strong>Add URI</strong> and
            paste this exactly:
            <CopyBox value={redirectUri} />
            <div className="steps__note">
              If your family reaches this app at more than one address, add one URI for each.
              A mismatch here is the cause of nearly every <code>redirect_uri_mismatch</code>{' '}
              error.
            </div>
          </li>
          <li>
            Press <strong>Create</strong>. Google shows a <strong>Client ID</strong> and{' '}
            <strong>Client secret</strong> — paste both into the boxes below.
          </li>
          <li>
            Each person then presses <strong>Connect an email</strong> and signs in. Google will
            warn that the app isn't verified; that's expected for something you host yourself —
            choose <strong>Advanced</strong> → <strong>Go to Family Calendar</strong>.
          </li>
        </ol>
      )}
    </div>
  )
}

function ExternalLink({ href, label }: { href: string; label?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {label ?? new URL(href).hostname.replace('www.', '')}
    </a>
  )
}

function CopyBox({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="copybox">
      <code>{value}</code>
      <button
        className="btn"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
          } catch {
            setCopied(false)
          }
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`
}
