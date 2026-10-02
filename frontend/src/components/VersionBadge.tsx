import { useState } from 'react'
import { useVersionPoll } from '../hooks/useVersionPoll'
import { dockerUpgradeHint, hasUpdate, safeReleaseUrl, versionBadgeLabel } from './updateNotice'

export function VersionBadge() {
  const { version, buildTime, update } = useVersionPoll()
  const [open, setOpen] = useState(false)
  const updateAvailable = update !== null && hasUpdate(update)
  const latest = update?.latest_version ?? ''
  const releaseUrl = safeReleaseUrl(update?.release_url)

  return (
    <>
      <button
        className={`version-badge${updateAvailable ? ' version-badge--update' : ''}`}
        onClick={() => setOpen(true)}
        aria-label={updateAvailable ? versionBadgeLabel(version, true) : 'About this app'}
      >
        <span>v{version}</span>
        {updateAvailable && (
          <>
            {/* The side rail is ~92px wide, so the notice sits under the version rather
                than beside it. A phone shows only the short word. */}
            <span className="version-badge__update version-badge__update--long">
              Update available
            </span>
            <span className="version-badge__update version-badge__update--short">Update</span>
          </>
        )}
      </button>
      {open && (
        <div className="about-popover" onClick={() => setOpen(false)} role="dialog">
          <div className="about-popover__card" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginTop: 0 }}>Family Calendar</h2>
            <p style={{ color: 'var(--text-dim)' }}>
              Version {version}
              {buildTime && (
                <>
                  <br />
                  Built {buildTime}
                </>
              )}
            </p>
            {updateAvailable && (
              <div className="about-popover__update">
                <strong>Update available: version {latest}</strong>
                {releaseUrl && (
                  <p>
                    <a href={releaseUrl} target="_blank" rel="noopener noreferrer">
                      See what changed
                    </a>
                  </p>
                )}
                <p>
                  To upgrade a Docker install: <code>{dockerUpgradeHint(latest)}</code>
                </p>
              </div>
            )}
            <p style={{ color: 'var(--text-dim)', fontSize: 'var(--font-sm)' }}>
              This screen updates itself automatically when a new version is deployed.
            </p>
            <button
              onClick={() => setOpen(false)}
              style={{
                background: 'var(--bg-elev-2)',
                borderRadius: 'var(--radius)',
                padding: '10px 24px',
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </>
  )
}
