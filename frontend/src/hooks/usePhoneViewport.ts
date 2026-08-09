import { useEffect, useState } from 'react'

/** Is this a phone rather than a screen that lives on a wall?
 *
 *  Measured on the *smaller* side, not the width. A phone held sideways is 844x390 --
 *  wider than most tablets are tall -- so a width test would decide a phone in
 *  landscape is a wall display and start a slideshow on it. The short side stays
 *  short whichever way the phone is turned, while a display's short side does not.
 */
export function isPhoneViewport(width: number, height: number, limit = 640): boolean {
  return Math.min(width, height) <= limit
}

/** Tracks it, because a phone rotates and a desktop window gets dragged. */
export function usePhoneViewport(): boolean {
  const [phone, setPhone] = useState(() =>
    isPhoneViewport(window.innerWidth, window.innerHeight),
  )

  useEffect(() => {
    const check = () => setPhone(isPhoneViewport(window.innerWidth, window.innerHeight))
    window.addEventListener('resize', check)
    window.addEventListener('orientationchange', check)
    return () => {
      window.removeEventListener('resize', check)
      window.removeEventListener('orientationchange', check)
    }
  }, [])

  return phone
}
