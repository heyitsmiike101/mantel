import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useSettings } from './api/hooks'
import { bookmarkLabel, safeBookmarkUrl } from './components/bookmark'
import { Screensaver } from './components/Screensaver'
import { VersionBadge } from './components/VersionBadge'
import { useBurnInShift } from './hooks/useIdle'
import { useOnline } from './hooks/useOnline'
import { useViewportFit } from './hooks/useViewportFit'

/** The four calendar views, each its own destination. A phone shows one entry for
 *  all of them instead — seven items plus a version badge do not fit across 390px,
 *  and the last one (Settings) was falling off the end. */
const CALENDAR_VIEWS = [
  { to: '/calendar/today', label: 'Today' },
  { to: '/calendar/3day', label: '3 Day' },
  { to: '/calendar/week', label: 'Week' },
  { to: '/calendar/month', label: 'Month' },
]

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/lists', label: 'Lists' },
  { to: '/settings', label: 'Settings' },
]

export function App() {
  const { data: settings } = useSettings()
  const onCalendar = useLocation().pathname.startsWith('/calendar')

  // Keeps the app the height of the space actually available, so a phone keyboard
  // never covers the nav or a modal's Save button.
  useViewportFit()

  const shift = useBurnInShift(settings?.burn_in_shift ?? false)
  const online = useOnline()

  // Optional shortcut to somewhere else in the house. No bookmark, no bar --
  // the grid row collapses, so nobody pays vertical space for a feature they
  // haven't set up. That matters on a wall display.
  const bookmark = safeBookmarkUrl(settings?.bookmark_url)

  useEffect(() => {
    document.documentElement.dataset.scale = settings?.display_scale ?? 'normal'
  }, [settings?.display_scale])

  return (
    <div
      className="shell"
      style={{ transform: `translate(${shift.x}px, ${shift.y}px)`, transition: 'transform 2s ease-in-out' }}
    >
      {bookmark && (
        <div className="topbar">
          <a className="topbar__link" href={bookmark} rel="noreferrer">
            <span aria-hidden>🔗</span>
            {bookmarkLabel(settings?.bookmark_label, bookmark)}
          </a>
        </div>
      )}
      <main className="shell__main">
        <Outlet />
      </main>
      <nav className="shell__nav">
        {/* One entry on a phone, four on anything larger. Both are rendered and the
            stylesheet picks -- a JS breakpoint would disagree with the CSS one that
            already decides whether this nav is a side rail or a bottom bar. */}
        <NavLink
          to="/calendar/today"
          className="navbtn navbtn--calendar"
          // Stays lit on every calendar view, not just Today, since it is now the
          // way back to all four.
          aria-current={onCalendar ? 'page' : undefined}
        >
          <span>Calendar</span>
        </NavLink>

        <span className="navviews">
          {CALENDAR_VIEWS.map((item) => (
            <NavLink key={item.to} to={item.to} className="navbtn">
              <span>{item.label}</span>
            </NavLink>
          ))}
        </span>

        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} className="navbtn">
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
