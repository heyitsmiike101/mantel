import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation, useUsers } from '../../api/hooks'
import type { LinkedAccount, SyncStatus } from '../../api/types'

/** Apple sign-in, which is nothing like Google's.
 *
 *  There is no OAuth for iCloud calendars and no developer account to create, so
 *  this tab has no household-wide setup step at all — no client ID, no secret, no
 *  redirect URI, and none of the LAN-address trouble that makes the Google tab as
 *  long as it is. Each person just needs an app-specific password from their own
 *  Apple ID, which takes about a minute.
 *
 *  The trade is that the password is a real credential rather than a scoped token,
 *  so it is checked against iCloud before anything is stored, and the only way to
 *  revoke it is at appleid.apple.com. Both are said plainly below. */
export function ICloudTab() {
  const { data: users = [] } = useUsers()
  const { data: accounts = [], refetch: refetchAccounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<LinkedAccount[]>('/accounts'),
  })
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatus>('/sync/status'),
    refetchInterval: 30_000,
  })

  const [connecting, setConnecting] = useState<number | null>(null)
  const [appleId, setAppleId] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSteps, setShowSteps] = useState<boolean | null>(null)

  const unlink = useEntityMutation(
    (id: number) => api.del<void>(`/accounts/${id}`),
    ['accounts', 'calendars', 'events', 'sync-status'],
  )

  const icloudAccounts = accounts.filter((a) => a.provider === 'icloud')
  const stepsOpen = showSteps ?? icloudAccounts.length === 0
  const needsReauth = new Set(status?.accounts_needing_reauth ?? [])

  const startConnecting = (userId: number) => {
    setConnecting(userId)
    setAppleId('')
    setPassword('')
    setError(null)
  }

  const submit = async (userId: number) => {
    setBusy(true)
    setError(null)
    try {
      await api.post('/accounts/icloud', {
        user_id: userId,
        apple_id: appleId.trim(),
        app_password: password,
      })
      setConnecting(null)
      setAppleId('')
      setPassword('')
      await Promise.all([refetchAccounts(), refetchStatus()])
    } catch (e) {
      // The API checks the password against iCloud before saving, so whatever comes
      // back here is the real reason and is safe to show as-is.
      setError(e instanceof Error ? e.message : 'Could not connect that Apple ID.')
    } finally {
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
      <h2>Apple Calendar</h2>
      <p className="hint">
        Optional, and worth it if your family is on iPhones. Events sync both ways: what you
        add here shows up in the Calendar app within seconds, and what they add on their phones
        shows up here. Unlike Google there is <strong>nothing to set up for the household</strong>{' '}
        — each person just makes an app-specific password for their own Apple ID.
      </p>

      <Steps open={stepsOpen} onToggle={() => setShowSteps(!stepsOpen)} />

      <h3 className="settings__h3">Connect an Apple ID</h3>
      <p className="hint">
        Each person connects their own, and can add as many as they like. An app-specific
        password only works for this app and can be cancelled at any time from your Apple ID
        page, without changing your real password.
      </p>

      {users.length === 0 && (
        <p className="banner banner--warn">
          Add your family under Settings → Family first, so there is somebody to connect an
          account to.
        </p>
      )}

      {icloudAccounts.some((a) => needsReauth.has(a.email)) && (
        <p className="banner banner--warn">
          These need connecting again:{' '}
          {icloudAccounts
            .filter((a) => needsReauth.has(a.email))
            .map((a) => a.email)
            .join(', ')}
          .
          <br />
          Apple cancels every app-specific password when the Apple ID password changes, so this
          is normal after changing it. Make a new one and connect again.
        </p>
      )}

      {users.map((u) => {
        const mine = icloudAccounts.filter((a) => a.user_id === u.id)
        return (
          <div key={u.id}>
            <div className="row">
              <div className="row__name row__name--static row__name--inline">
                <span className="swatch" style={{ background: u.color }} />
                <div>
                  <div>{u.name}</div>
                  <div className="hint">
                    {mine.length === 0
                      ? 'No Apple ID connected'
                      : mine
                          .map(
                            (a) =>
                              `${a.email}${needsReauth.has(a.email) ? ' (needs reconnecting)' : ''}`,
                          )
                          .join(', ')}
                  </div>
                </div>
              </div>
              {mine.map((a) => (
                <button
                  key={a.id}
                  className="btn btn--danger"
                  onClick={() => unlink.mutate(a.id)}
                  title="Removes the calendars from this app. Nothing is deleted from iCloud."
                >
                  Unlink {a.email.split('@')[0]}
                </button>
              ))}
              <button
                className="btn btn--primary"
                disabled={busy}
                onClick={() => startConnecting(u.id)}
              >
                {mine.length === 0 ? 'Connect an Apple ID' : 'Add another'}
              </button>
            </div>

            {connecting === u.id && (
              <div className="row">
                <div className="row__name row__name--static">
                  Apple ID and app-specific password
                  <div className="hint">Step 3 above, if you have not made one yet.</div>
                </div>
                <input
                  className="row__name"
                  type="email"
                  autoComplete="off"
                  placeholder="you@icloud.com"
                  value={appleId}
                  onChange={(e) => setAppleId(e.target.value)}
                />
                <input
                  className="row__name"
                  type="password"
                  autoComplete="off"
                  placeholder="abcd-efgh-ijkl-mnop"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && appleId && password) submit(u.id)
                  }}
                />
                <button
                  className="btn btn--primary"
                  disabled={busy || !appleId.trim() || !password.trim()}
                  onClick={() => submit(u.id)}
                >
                  {busy ? 'Checking…' : 'Connect'}
                </button>
                <button className="btn" disabled={busy} onClick={() => setConnecting(null)}>
                  Cancel
                </button>
              </div>
            )}
          </div>
        )
      })}

      {error && <p className="banner banner--warn">{error}</p>}

      {/* Which calendars are shown, who owns them, and whether each one syncs all live
          in Settings -> Calendars. This tab is about the connection to Apple. */}
      {status && (
        <div className="row">
          <div className="row__name row__name--static hint">
            Syncs every {Math.round(status.interval_seconds / 60)} min
            {status.pending_pushes > 0 && ` · ${status.pending_pushes} change(s) to send`}
          </div>
          <button className="btn" onClick={syncNow} disabled={busy}>
            {busy ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      )}
    </section>
  )
}

function Steps({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div className="steps">
      <button className="btn steps__toggle" onClick={onToggle}>
        {open ? 'Hide the steps' : 'Show me how (about a minute)'}
      </button>
      {!open ? null : (
        <ol className="steps__list">
          <li>
            Go to{' '}
            <a href="https://appleid.apple.com" target="_blank" rel="noreferrer">
              appleid.apple.com
            </a>{' '}
            and sign in with the Apple ID whose calendars you want here.
          </li>
          <li>
            Under <strong>Sign-In and Security</strong>, open{' '}
            <strong>App-Specific Passwords</strong>. If you do not see it, two-factor
            authentication is not switched on for the Apple ID — Apple requires it, and turning
            it on is on the same page.
          </li>
          <li>
            Press <strong>+</strong>, name it something you will recognise later like
            “Mantel”, and Apple shows you a password in four groups, like{' '}
            <code>abcd-efgh-ijkl-mnop</code>. It is only shown once.
          </li>
          <li>
            Paste it below with the Apple ID. It is checked against iCloud straight away, so
            you will know immediately if something is off, and it is stored encrypted.
          </li>
          <li>
            Open <strong>Settings → Calendars</strong> to choose which of the calendars to show
            and who each one belongs to. They all arrive switched off, so nothing lands on the
            wall display until you say so.
          </li>
        </ol>
      )}
      {open && (
        <p className="hint">
          To take access away later, delete the password on that same Apple ID page — unlinking
          here removes the calendars from this app but cannot cancel the password for you.
        </p>
      )}
    </div>
  )
}
