import { useEffect, useState } from 'react'

const ACTIVITY_EVENTS = [
  'pointerdown',
  'pointermove',
  'keydown',
  'wheel',
  'touchstart',
] as const

/**
 * True once nothing has touched the screen for `timeoutMs`. Used to drop a wall
 * display into the screensaver.
 *
 * The timer is reset on a plain ref-free interval rather than per event so a
 * finger dragging across a touchscreen doesn't reschedule a timeout hundreds of
 * times a second.
 */
export function useIdle(timeoutMs: number, enabled = true): boolean {
  const [idle, setIdle] = useState(false)

  useEffect(() => {
    if (!enabled || timeoutMs <= 0) {
      setIdle(false)
      return
    }

    let lastActivity = Date.now()
    const markActive = () => {
      lastActivity = Date.now()
    }

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, markActive, { passive: true })
    }

    const tick = setInterval(() => {
      setIdle(Date.now() - lastActivity >= timeoutMs)
    }, 1000)

    return () => {
      clearInterval(tick)
      for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, markActive)
    }
  }, [timeoutMs, enabled])

  return idle
}

/**
 * True when the current local time falls inside the nightly sleep window.
 * Handles windows that cross midnight (23 -> 7), which is the normal case.
 */
export function isWithinSleepWindow(startHour: number, endHour: number, now = new Date()): boolean {
  const hour = now.getHours() + now.getMinutes() / 60
  if (startHour === endHour) return false
  return startHour < endHour
    ? hour >= startHour && hour < endHour
    : hour >= startHour || hour < endHour
}

export function useSleepWindow(enabled: boolean, startHour: number, endHour: number): boolean {
  const [asleep, setAsleep] = useState(() =>
    enabled ? isWithinSleepWindow(startHour, endHour) : false,
  )

  useEffect(() => {
    if (!enabled) {
      setAsleep(false)
      return
    }
    const check = () => setAsleep(isWithinSleepWindow(startHour, endHour))
    check()
    const timer = setInterval(check, 30_000)
    return () => clearInterval(timer)
  }, [enabled, startHour, endHour])

  return asleep
}

/**
 * Nudges the whole page a few pixels every 10 minutes. An always-on panel showing
 * a static grid will ghost otherwise, and shifting is far less intrusive than
 * blanking the display someone mounted specifically to be looked at.
 */
export function useBurnInShift(enabled: boolean): { x: number; y: number } {
  const [offset, setOffset] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (!enabled) {
      setOffset({ x: 0, y: 0 })
      return
    }
    let step = 0
    const shift = () => {
      // Walk a small diamond so every pixel spends time showing background.
      const pattern = [
        { x: 0, y: 0 },
        { x: 4, y: 2 },
        { x: 0, y: 4 },
        { x: -4, y: 2 },
      ]
      setOffset(pattern[step % pattern.length])
      step += 1
    }
    const timer = setInterval(shift, 10 * 60_000)
    return () => clearInterval(timer)
  }, [enabled])

  return offset
}
