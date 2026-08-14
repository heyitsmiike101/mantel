import { useEffect } from 'react'

/** Should the page scroll itself back to the top?
 *
 *  When a phone keyboard opens, the browser scrolls the *layout* viewport to bring the
 *  focused field into view. Closing the keyboard gives the height back but leaves that
 *  scroll behind, so the app sits shifted up with a strip of blank page below the nav
 *  until you scroll it back by hand. Growing back past where we started means the
 *  keyboard has gone, and the offset it left is no longer wanted.
 *
 *  The tolerance keeps this from firing on the small height changes that are not a
 *  keyboard -- a URL bar collapsing as you scroll, an orientation nudge.
 */
export function shouldSnapBack(previous: number, next: number, tolerance = 80): boolean {
  return next - previous > tolerance
}

/** Is something -- in practice the keyboard -- covering part of the window?
 *
 *  The visual viewport being materially shorter than the layout viewport is what an
 *  open keyboard looks like. The threshold skips the few pixels of disagreement that
 *  are normal on desktop, and a collapsing mobile URL bar, neither of which should
 *  make the app start overriding its own height.
 */
export function keyboardIsUp(layoutHeight: number, visualHeight: number, threshold = 80): boolean {
  return layoutHeight - visualHeight > threshold
}

/** Keeps the app exactly as tall as the space actually available.
 *
 *  `height: 100%` measures the layout viewport, which on iOS does not shrink when the
 *  keyboard appears -- so the bottom nav and a modal's Save button end up underneath
 *  it, out of reach. visualViewport reports the real number.
 *
 *  Publishes it as `--app-height` rather than reflowing from JS, so the stylesheet
 *  stays in charge of what uses it. On a wall display and on desktop this equals the
 *  window height and nothing changes.
 */
export function useViewportFit(): void {
  useEffect(() => {
    const vv = window.visualViewport
    let previous = vv?.height ?? window.innerHeight

    const apply = () => {
      const height = vv?.height ?? window.innerHeight

      if (keyboardIsUp(window.innerHeight, height)) {
        document.documentElement.style.setProperty('--app-height', `${height}px`)
        // Height alone is not enough. iOS scrolls the *layout* viewport to reveal the
        // focused field, so the visible area starts partway down the page: a shell
        // pinned to the layout viewport's origin then has its top scrolled out of
        // sight and its bottom cut off by the keyboard. offsetTop is how far the
        // visible area has moved, and putting the shell there realigns the two.
        document.documentElement.style.setProperty('--app-offset', `${vv?.offsetTop ?? 0}px`)
      } else {
        // Nothing is covering the screen, so hand the height back to CSS rather than
        // pinning a pixel value. A stale pinned value is the worst outcome available
        // -- the app stays shrunk with dead space below it until something else fires
        // an event -- and this way a missed event costs nothing, because `100%` is
        // already correct whenever the keyboard is down.
        document.documentElement.style.removeProperty('--app-height')
        document.documentElement.style.removeProperty('--app-offset')
      }

      if (shouldSnapBack(previous, height)) {
        // The keyboard has closed. Undo the scroll it caused, on the next frame so
        // it runs after the browser has finished its own adjustment.
        requestAnimationFrame(() => window.scrollTo(0, 0))
      }
      previous = height
    }

    apply()

    if (vv) {
      vv.addEventListener('resize', apply)
      // The keyboard also *scrolls* the visual viewport without resizing it, which is
      // what happens when focus moves between two fields while it is already open.
      vv.addEventListener('scroll', apply)
    }
    // Not redundant. A keyboard fires the visualViewport events, but dragging a
    // desktop window, rotating a tablet, or a browser resizing its own chrome only
    // fires this one -- and without it --app-height sticks at whatever it was when
    // the page loaded, leaving the nav off the bottom of the screen.
    window.addEventListener('resize', apply)
    window.addEventListener('orientationchange', apply)

    // Focus is the only signal that is guaranteed to arrive when the keyboard opens
    // and closes. The viewport events are the accurate ones, but Safari has shipped
    // versions that delay them or skip the close entirely, and being wrong there
    // means the app stays shrunk with dead space under it. Re-measuring after the
    // keyboard's animation costs nothing and makes the snap-back certain.
    const timers: number[] = []
    const onFocusChange = () => {
      apply()
      timers.push(window.setTimeout(apply, 150), window.setTimeout(apply, 400))
    }
    document.addEventListener('focusin', onFocusChange)
    document.addEventListener('focusout', onFocusChange)

    return () => {
      if (vv) {
        vv.removeEventListener('resize', apply)
        vv.removeEventListener('scroll', apply)
      }
      window.removeEventListener('resize', apply)
      window.removeEventListener('orientationchange', apply)
      document.removeEventListener('focusin', onFocusChange)
      document.removeEventListener('focusout', onFocusChange)
      timers.forEach(clearTimeout)
    }
  }, [])
}
