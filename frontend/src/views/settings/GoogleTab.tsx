import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import type { AppSettings, LinkedAccount, SyncStatus } from '../../api/types'
import { googleRedirectProblem, localhostAlternative, tunnelCommand } from './googleRedirect'

export function GoogleTab() {
  const { data: settings } = useSettings()
  const { data: users = [] } = useUsers()
  const { data: allAccounts = [], refetch: refetchAccounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.get<LinkedAccount[]>('/accounts'),
  })
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get<SyncStatus>('/sync/status'),
    refetchInterval: 30_000,
  })

  const [busy, setBusy] = useState(false)
  // The OAuth callback can only talk to us through the URL it redirects to, so
  // anything that went wrong over at Google arrives as ?error=<code>.
  const [error, setError] = useState<string | null>(() =>
    describeCallbackError(new URLSearchParams(window.location.search).get('error')),
  )
  // null means "nobody has clicked the toggle yet", so the walkthrough can be open
  // by default for someone who hasn't set Google up and closed for someone who has.
  const [showSteps, setShowSteps] = useState<boolean | null>(null)

  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings'],
  )
  const unlink = useEntityMutation(
    (id: number) => api.del<void>(`/accounts/${id}`),
    ['accounts', 'calendars', 'events', 'sync-status'],
  )

  const accounts = allAccounts.filter((a) => a.provider === 'google')
  // The status list covers every provider; an Apple ID that needs reconnecting is
  // the Apple tab's problem, and the Google advice below would be wrong for it.
  const staleGoogle = accounts
    .filter((a) => (status?.accounts_needing_reauth ?? []).includes(a.email))
    .map((a) => a.email)

  if (!settings) return null

  const configured = settings.server.google_configured
  const stepsOpen = showSteps ?? !configured
  // Defaulting to the address this browser is on is almost always the right
  // answer, and it is the value Google must be told about verbatim.
  const baseUrl = settings.public_base_url || window.location.origin
  const redirectUri = `${baseUrl.replace(/\/$/, '')}/api/accounts/google/callback`
  // Google refuses most of what a LAN install looks like. Say so here rather than
  // letting the console say "Invalid Redirect" after they've followed the steps.
  const redirectProblem = googleRedirectProblem(baseUrl)
  const tunnel = tunnelCommand(baseUrl)

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

      <Steps
        open={stepsOpen}
        onToggle={() => setShowSteps(!stepsOpen)}
        redirectUri={redirectUri}
        baseUrl={baseUrl}
      />

      <h3 className="settings__h3">Your Google credentials</h3>

      <div className="row">
        <div className="row__name row__name--static">
          This app's address
          <div className="hint">
            How your family reaches this app. The redirect URI you gave Google must match it.
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

      {redirectProblem && (
        <p className="banner banner--warn">
          <strong>Google will refuse this redirect URI.</strong> {redirectProblem}
          <br />
          <br />
          The redirect only matters while somebody is connecting an account, so the usual fix
          costs nothing: register{' '}
          <code>{localhostAlternative(baseUrl)}/api/accounts/google/callback</code> in Google,
          put <code>{localhostAlternative(baseUrl)}</code> in the box above, and do the connect
          step from a browser on the machine running this app — or through an SSH tunnel:
          {tunnel && <CopyBox value={tunnel} />}
          Then open <code>{localhostAlternative(baseUrl)}/settings?tab=google</code> and press
          Connect. Everyday use at <code>{baseUrl}</code> is unaffected, and syncing keeps
          working afterwards — refreshing a token doesn't use the redirect URI.
        </p>
      )}

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

      {staleGoogle.length > 0 && (
        <p className="banner banner--warn">
          These need connecting again: {staleGoogle.join(', ')}.
          <br />
          If this keeps happening about once a week, your Google app is still in{' '}
          <strong>Testing</strong> mode, which expires connections after 7 days. Open{' '}
          <a
            href="https://console.cloud.google.com/auth/audience"
            target="_blank"
            rel="noreferrer"
          >
            Google Auth Platform → Audience
          </a>{' '}
          and press <strong>Publish app</strong> — see step 4 of the walkthrough above.
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

      {/* Which calendars are shown, who owns them, and whether each one syncs all live
          in Settings -> Calendars. This tab is about the connection to Google. */}
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

/** Turn a callback error code into something a person can act on.
 *
 *  `no_calendar_scope` is the one worth spelling out. Google hands back a valid
 *  token with the calendar permission quietly removed when the project can't
 *  grant it, so the sign-in looks like it worked and nothing syncs. The two
 *  causes are both one checkbox in the console, and neither is guessable. */
function describeCallbackError(code: string | null): string | null {
  if (!code) return null
  switch (code) {
    case 'no_calendar_scope':
      return (
        'Google signed you in but did not grant calendar access, so there is nothing to ' +
        'sync. Two things to check in the Google console: that the Google Calendar API is ' +
        'enabled for the project (APIs & Services → Library), and that ' +
        'https://www.googleapis.com/auth/calendar is listed under Google Auth Platform → ' +
        'Data Access. Fix either one, then connect again.'
      )
    case 'calendar_list_failed':
      return (
        "Your account linked, but Google refused to list its calendars. That is usually the " +
        'Google Calendar API not being enabled for the project. Enable it, then press ' +
        'Sync now — there is no need to reconnect.'
      )
    case 'access_denied':
      return (
        'Google sign-in was cancelled. If you did not cancel it, the account may not be on ' +
        "the test-user list while the app is still in Testing mode — publishing the app " +
        '(step 4) is the usual fix.'
      )
    default:
      return `Google returned an error: ${code}`
  }
}

function Steps({
  open,
  onToggle,
  redirectUri,
  baseUrl,
}: {
  open: boolean
  onToggle: () => void
  redirectUri: string
  baseUrl: string
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
            Open the{' '}
            <ExternalLink
              href="https://console.cloud.google.com/auth/overview"
              label="Google Auth Platform"
            />{' '}
            and press <strong>Get started</strong>. Give it an app name and pick your own
            address as the support email, choose <strong>External</strong> for the audience,
            and enter your email again as the contact.
          </li>
          <li>
            <strong>Publish the app.</strong> Go to{' '}
            <ExternalLink
              href="https://console.cloud.google.com/auth/audience"
              label="Google Auth Platform → Audience"
            />
            . It will say <strong>Testing</strong> — press <strong>Publish app</strong> and
            confirm, so it reads <strong>In production</strong>.
            <div className="steps__note steps__note--warn">
              Do not skip this. While the app is in Testing, Google <strong>expires every
              connection after 7 days</strong>, so your whole family has to reconnect once a
              week, and you are capped at 100 test users. Publishing does not send your app for
              review — a calendar app used only by your own household needs no verification. It
              stays private to whoever you give the URL to.
            </div>
          </li>
          <li>
            Go to{' '}
            <ExternalLink
              href="https://console.cloud.google.com/auth/clients"
              label="Google Auth Platform → Clients"
            />{' '}
            → <strong>Create client</strong> → application type{' '}
            <strong>Web application</strong>.
          </li>
          <li>
            Under <strong>Authorized redirect URIs</strong>, press <strong>Add URI</strong> and
            paste this exactly:
            <CopyBox value={redirectUri} />
            <div className="steps__note steps__note--warn">
              Google only accepts <code>http://</code> for <code>localhost</code>, rejects IP
              addresses, and requires a hostname ending in a public domain such as{' '}
              <code>.com</code>. A normal LAN address —{' '}
              <code>http://192.168.1.50:8080</code>, <code>http://calendar.local</code>, a bare
              machine name — is refused with <em>"must end with a public top-level domain"</em>.
              If that is you, register{' '}
              <code>{localhostAlternative(baseUrl)}/api/accounts/google/callback</code> instead
              and do the connect step over an SSH tunnel; the box below the steps explains it.
            </div>
            <div className="steps__note">
              If your family reaches this app at more than one accepted address, add one URI for
              each. A mismatch is the cause of nearly every{' '}
              <code>redirect_uri_mismatch</code> error.
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
