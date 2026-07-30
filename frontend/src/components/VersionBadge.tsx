import { useState } from 'react'
import { useVersionPoll } from '../hooks/useVersionPoll'

export function VersionBadge() {
  const { version, buildTime } = useVersionPoll()
  const [open, setOpen] = useState(false)

  return (
    <>
      <button className="version-badge" onClick={() => setOpen(true)} aria-label="About this app">
        v{version}
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
