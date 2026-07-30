import { useEffect, useState } from 'react'

/**
 * Whether the app can currently reach the server.
 *
 * `navigator.onLine` alone is not enough: a kiosk tablet still associated with a
 * dead router reports itself online. So the "offline" state is only cleared by an
 * actual successful request, which the version poll is already making every
 * minute anyway.
 */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const goOnline = () => setOnline(true)
    const goOffline = () => setOnline(false)

    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    window.addEventListener('famcal:reachable', goOnline)
    window.addEventListener('famcal:unreachable', goOffline)

    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('famcal:reachable', goOnline)
      window.removeEventListener('famcal:unreachable', goOffline)
    }
  }, [])

  return online
}
