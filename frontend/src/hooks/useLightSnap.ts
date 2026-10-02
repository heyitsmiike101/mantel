import { useLayoutEffect, useRef, type RefObject } from 'react'

/** "Near the boundary of a unit" for the light snap: within 12% of a unit's size, in either
 *  direction. Wide enough that a slightly-off stop tidies itself up, narrow enough that
 *  stopping mid-way (to read the middle of a month) stays put. */
export const SNAP_FRACTION = 0.12

/** The pull of a scroller's home position (Week/3 Day: today's default view), as a
 *  fraction of a unit. Medium rather than light: coming back to "now" should land on it
 *  without having to be lined up by hand, but a distant stop is still left alone. */
export const HOME_FRACTION = 0.5

/** Quiet period after the last scroll event before we treat the scroll as settled, for
 *  browsers without the `scrollend` event. */
const SETTLE_MS = 150

/** A button-driven scroll is "in flight" until it arrives or this long passes, so the
 *  snap never fights it. */
const PROGRAMMATIC_MS = 1500

export const prefersReducedMotion = () =>
  typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/** The units the scroller is made of, measured fresh at each settle because sizes change
 *  with the window and the display. `at(i)` is the scroll position that puts unit `i` at
 *  the edge; every unit is `size` long, which is what makes "which boundary is next" a
 *  division rather than a search. */
export interface SnapUnits {
  size: number
  count: number
  at: (index: number) => number
  /** Optional scroll position with a stronger pull (HOME_FRACTION), e.g. today's view. */
  home?: number | null
}

interface Options {
  axis: 'x' | 'y'
  measure: () => SnapUnits | null
}

/**
 * Light snap for an infinite scroller: once scrolling settles, a unit boundary within
 * SNAP_FRACTION of a unit pulls the view onto it. Done in JS rather than CSS scroll-snap,
 * whose `proximity` mode in Chromium is far from light and traps slow wheel scrolling.
 *
 * Returns `rest` (the position the next scroll starts from; callers that move the scroller
 * themselves must keep it in step) and `scrollTo`, which marks a scroll as programmatic so
 * the snap leaves it alone.
 */
export function useLightSnap(ref: RefObject<HTMLElement | null>, { axis, measure }: Options) {
  // Scroll position when the last scroll settled, i.e. where the next one starts. The snap
  // needs it to tell the boundary a scroll left from the one it reached for.
  const rest = useRef(0)
  // Set while a requested (button) scroll is travelling; the snap stays out of its way.
  const inflight = useRef<{ to: number; until: number } | null>(null)
  // The caller's measure() changes identity every render; the listeners must not be
  // re-bound each time (a re-bind mid-fling drops events), so they read it through a ref.
  const measureRef = useRef(measure)
  measureRef.current = measure

  const pos = (el: HTMLElement) => (axis === 'x' ? el.scrollLeft : el.scrollTop)

  const scrollTo = (to: number) => {
    const el = ref.current
    if (!el) return
    inflight.current = { to, until: Date.now() + PROGRAMMATIC_MS }
    // Someone who asked their OS not to animate gets an instant jump.
    const behavior = prefersReducedMotion() ? 'auto' : 'smooth'
    el.scrollTo(axis === 'x' ? { left: to, behavior } : { top: to, behavior })
  }
  const scrollToRef = useRef(scrollTo)
  scrollToRef.current = scrollTo

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    let touching = false
    // The scroll being settled came from a finger (set on touchstart, cleared by settle).
    let byTouch = false
    let timer = 0
    rest.current = pos(el)

    const settle = () => {
      timer = 0
      if (touching) return
      const flight = inflight.current
      if (flight) {
        // A button scroll is travelling: wait for it to arrive (or time out).
        if (Math.abs(pos(el) - flight.to) > 1 && Date.now() < flight.until) return
        inflight.current = null
      }
      const units = measureRef.current()
      if (!units || units.size === 0 || units.count === 0) return
      // Where this scroll started matters. A mouse-wheel notch is ~100px, under the snap
      // distance, and each notch settles on its own -- so snapping to the *nearest*
      // boundary pulled every notch straight back to the unit it left, and on a tall
      // portrait screen the wheel could not get anywhere. Only boundaries this scroll
      // reached for count: the one ahead of it, or one it crossed and slightly overshot.
      // Never the one it started on.
      const from = rest.current
      const st = pos(el)
      const bh = units.size
      const below = Math.min(units.count - 1, Math.max(0, Math.floor(st / bh)))
      const behind = units.at(below)
      const ahead = units.at(Math.min(units.count - 1, below + 1))
      let target: number | null = null
      const home = units.home
      // Home pulls only a scroll that is coming back to it -- one that got closer or
      // crossed it. A scroll leaving home is never yanked back, or every wheel notch
      // away from today would land on today again.
      const towardHome =
        home != null &&
        Math.abs(st - home) <= bh * HOME_FRACTION &&
        Math.abs(from - home) > 1 &&
        (Math.abs(st - home) < Math.abs(from - home) - 1 || (st - home) * (from - home) < 0)
      if (towardHome) {
        byTouch = false
        target = home
      } else if (byTouch) {
        // A finger moves continuously rather than in notches, so a short drag let go
        // near where it started should settle back: plain nearest boundary.
        byTouch = false
        const near = st - behind <= ahead - st ? behind : ahead
        if (Math.abs(near - st) <= bh * SNAP_FRACTION) target = near
      } else if (st > from) {
        if (ahead - st <= bh * SNAP_FRACTION) target = ahead
        else if (from < behind - 1 && st - behind <= bh * SNAP_FRACTION) target = behind
      } else if (st < from) {
        if (st - behind <= bh * SNAP_FRACTION) target = behind
        else if (from > ahead + 1 && ahead - st <= bh * SNAP_FRACTION) target = ahead
      }
      // > 1px also stops the snap re-triggering itself once it has arrived.
      if (target !== null && Math.abs(target - st) > 1) {
        rest.current = target
        const behavior = prefersReducedMotion() ? 'auto' : 'smooth'
        el.scrollTo(axis === 'x' ? { left: target, behavior } : { top: target, behavior })
      } else {
        rest.current = st
      }
    }
    const settleSoon = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(settle, SETTLE_MS)
    }
    const hasScrollEnd = 'onscrollend' in window

    const onScroll = () => {
      if (!hasScrollEnd) settleSoon()
    }
    // Touch events, not pointer events: once the browser takes a touch over to scroll it
    // fires pointercancel straight away, which would look like the finger lifting while
    // it is still on the glass. touchend/touchcancel only come when it really leaves.
    const onDown = () => {
      inflight.current = null
      touching = true
      byTouch = true
    }
    const onUp = () => {
      touching = false
      // A drag that ends without momentum may not produce another scroll event.
      settleSoon()
    }
    // Grabbing the wheel mid-button-scroll hands control back to the user.
    const onWheel = () => {
      inflight.current = null
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    if (hasScrollEnd) el.addEventListener('scrollend', settle)
    el.addEventListener('touchstart', onDown, { passive: true })
    el.addEventListener('touchend', onUp, { passive: true })
    el.addEventListener('touchcancel', onUp, { passive: true })
    el.addEventListener('wheel', onWheel, { passive: true })
    return () => {
      el.removeEventListener('scroll', onScroll)
      el.removeEventListener('scrollend', settle)
      el.removeEventListener('touchstart', onDown)
      el.removeEventListener('touchend', onUp)
      el.removeEventListener('touchcancel', onUp)
      el.removeEventListener('wheel', onWheel)
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { rest, scrollTo: (to: number) => scrollToRef.current(to) }
}
