import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { App } from './App'
import './styles/global.css'
import './styles/calendar.css'
import './styles/settings.css'
import './styles/dashboard.css'
import './styles/screensaver.css'
import { CalendarPage } from './views/calendar/CalendarPage'
import { DashboardPage } from './views/dashboard/DashboardPage'
import { DocsPage } from './views/docs/DocsPage'
import { SettingsPage } from './views/settings/SettingsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchInterval: 60_000, refetchOnWindowFocus: true, staleTime: 15_000, retry: 1 },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/calendar/week" replace /> },
      { path: 'calendar/:view', element: <CalendarPage /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'docs', element: <DocsPage /> },
      { path: '*', element: <Navigate to="/calendar/week" replace /> },
    ],
  },
])

// Registered after load so the worker never competes with the first paint.
// The worker deliberately leaves /api/version alone -- see public/sw.js.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js')
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
