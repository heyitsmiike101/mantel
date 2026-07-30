import { useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useSettings } from './api/hooks'
import { VersionBadge } from './components/VersionBadge'

const NAV = [
  { to: '/calendar/today', icon: '📅', label: 'Today' },
  { to: '/calendar/3day', icon: '🗓️', label: '3 Day' },
  { to: '/calendar/week', icon: '📆', label: 'Week' },
  { to: '/calendar/month', icon: '🈷️', label: 'Month' },
  { to: '/dashboard', icon: '🧩', label: 'Dashboard' },
  { to: '/settings', icon: '⚙️', label: 'Settings' },
  { to: '/docs', icon: '📖', label: 'API' },
]

export function App() {
  const { data: settings } = useSettings()

  useEffect(() => {
    document.documentElement.dataset.scale = settings?.display_scale ?? 'normal'
  }, [settings?.display_scale])

  return (
    <div className="shell">
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
    </div>
  )
}
