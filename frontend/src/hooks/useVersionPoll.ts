import { useEffect, useRef, useState } from 'react'
import { api, type VersionInfo } from '../api/client'

const POLL_MS = 60_000

/** Blocks the auto-reload while a form has unsaved input. Incremented/decremented by
 *  modals via useReloadGuard so a kiosk never discards someone's half-typed event. */
let reloadGuards = 0
export function acquireReloadGuard() {
  reloadGuards += 1
  return () => {
    reloadGuards -= 1
  }
}

/**
 * Detects a new deployment and hard-reloads the page. Kiosk displays have no keyboard,
 * so this is the only way a wall-mounted tablet picks up a new version.
 */
export function useVersionPoll() {
  const [version, setVersion] = useState<string>(import.meta.env.VITE_APP_VERSION ?? 'dev')
  const [buildTime, setBuildTime] = useState<string>('')
  const baseline = useRef<string | null>(null)
  const pendingReload = useRef(false)

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const info = await api.get<VersionInfo>('/version')
        if (cancelled) return
        setVersion(info.version)
        setBuildTime(info.build_time)
        if (baseline.current === null) {
          baseline.current = info.version
          return
        }
        if (info.version !== baseline.current) pendingReload.current = true
      } catch {
        /* server restarting mid-deploy; try again next tick */
      }
      if (pendingReload.current && reloadGuards === 0) window.location.reload()
    }

    void check()
    const timer = setInterval(check, POLL_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return { version, buildTime }
}
