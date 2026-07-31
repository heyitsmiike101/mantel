import { useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useSettings } from './api/hooks'
import { Screensaver } from './components/Screensaver'
import { VersionBadge } from './components/VersionBadge'
import { useBurnInShift } from './hooks/useIdle'
import { useOnline } from './hooks/useOnline'

const NAV = [
  { to: '/calendar/today', icon: '📅', label: 'Today' },
  { to: '/calendar/3day', icon: '🗓️', label: '3 Day' },
  { to: '/calendar/week', icon: '📆', label: 'Week' },
  { to: '/calendar/month', icon: '🈷️', label: 'Month' },
  { to: '/dashboard', icon: '🧩', label: 'Dashboard' },
  { to: '/lists', icon: '🛒', label: 'Lists' },
  { to: '/settings', icon: '⚙️', label: 'Settings' },
]

export function App() {
  const { data: settings } = useSettings()

  const shift = useBurnInShift(settings?.burn_in_shift ?? false)
  const online = useOnline()

  useEffect(() => {
    document.documentElement.dataset.scale = settings?.display_scale ?? 'normal'
  }, [settings?.display_scale])

  return (
    <div
      className="shell"
      style={{ transform: `translate(${shift.x}px, ${shift.y}px)`, transition: 'transform 2s ease-in-out' }}
    >
      <main className="shell__main">
        <Outlet />
      </main>
      <nav className="shell__nav">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} className="navbtn">
            <span className="navbtn__icon" aria-hidden>
              {item.icon}
            </span>
            <span>{item.label}</span>
          </NavLink>
        ))}
        <VersionBadge />
      </nav>
      {!online && <div className="offline">Offline — showing the last known schedule</div>}
      <Screensaver />
    </div>
  )
}
