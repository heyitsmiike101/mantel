import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import type { CalendarInfo } from '../../api/types'

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

export function AccountsTab() {
  const { data: settings } = useSettings()
  const { data: users = [] } = useUsers()
  const { data: accounts = [], refetch: refetchAccounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<LinkedAccount[]>('/accounts'),
  })
  const { data: calendars = [] } = useCalendars()
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatus>('/sync/status'),
    refetchInterval: 30_000,
  })

  const [linkingUser, setLinkingUser] = useState<number | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const unlink = useEntityMutation(
    (id: number) => api.del<void>(`/accounts/${id}`),
    ['accounts', 'calendars', 'events', 'sync-status'],
  )
  const updateCal = useEntityMutation(
    ({ id, ...patch }: { id: number } & Partial<CalendarInfo>) =>
      api.patch<CalendarInfo>(`/calendars/${id}`, patch),
    ['calendars', 'events', 'sync-status'],
  )

  const configured = settings?.server.google_configured ?? false

  const startLink = async () => {
    if (linkingUser === '') return setError('Pick who this Google account belongs to first.')
    setError(null)
    setBusy(true)
    try {
      const { url } = await api.get<{ url: string }>(`/accounts/google/auth-url?user_id=${linkingUser}`)
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
      <h2>Google accounts</h2>

      {!configured && (
        <p className="hint">
          Google sync isn't set up yet. Add <code>GOOGLE_CLIENT_ID</code> and{' '}
          <code>GOOGLE_CLIENT_SECRET</code> to your <code>.env</code> file and restart —
          see <code>docs/setup-google-oauth.md</code> for the step-by-step walkthrough.
        </p>
      )}

      {status && status.accounts_needing_reauth.length > 0 && (
        <p className="banner banner--warn">
          These accounts need to be connected again: {status.accounts_needing_reauth.join(', ')}
        </p>
      )}

      {accounts.map((a) => (
        <div key={a.id} className="row">
          <div className="row__name row__name--static">
            <div>{a.email}</div>
            <div className="hint">
              {users.find((u) => u.id === a.user_id)?.name ?? 'Unknown'} ·{' '}
              {a.status === 'active' ? 'Connected' : 'Needs reconnecting'}
            </div>
          </div>
          <button className="btn btn--danger" onClick={() => unlink.mutate(a.id)}>
            Unlink
          </button>
        </div>
      ))}

      {configured && (
        <div className="row">
          <select
            value={linkingUser}
            onChange={(e) => setLinkingUser(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">Who is this account for?</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          <button className="btn btn--primary" onClick={startLink} disabled={busy}>
            Connect a Google account
          </button>
        </div>
      )}

      {error && <p className="banner banner--warn">{error}</p>}

      <h2 style={{ marginTop: 24 }}>Google calendars</h2>
      <p className="hint">
        Turn on the calendars you want synced. Events sync both ways: changes made here appear
        in Google within seconds, and vice versa.
      </p>

      {calendars.filter((c) => !c.is_local).length === 0 && (
        <p className="hint">No Google calendars yet — connect an account above.</p>
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
                  {!c.writable && ' · read-only'}
                  {cal?.last_synced_at && ` · synced ${timeAgo(cal.last_synced_at)}`}
                  {cal?.sync_error && ` · ${cal.sync_error.slice(0, 80)}`}
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
            Syncs automatically every {Math.round(status.interval_seconds / 60)} min
            {status.pending_pushes > 0 && ` · ${status.pending_pushes} change(s) waiting to send`}
          </div>
          <button className="btn" onClick={syncNow} disabled={busy || !configured}>
            {busy ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      )}
    </section>
  )
}

function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`
}
