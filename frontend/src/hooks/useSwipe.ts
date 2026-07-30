import { useRef, type PointerEvent } from 'react'

const MIN_DISTANCE = 60
const MAX_OFF_AXIS = 80

/** Horizontal swipe to move through dates. Deliberately ignores mostly-vertical drags so
 *  scrolling a day column never changes the date. */
export function useSwipe(onSwipe: (direction: 1 | -1) => void) {
  const origin = useRef<{ x: number; y: number } | null>(null)

  return {
    onPointerDown: (e: PointerEvent) => {
      if (e.pointerType === 'mouse' && e.button !== 0) return
      origin.current = { x: e.clientX, y: e.clientY }
    },
    onPointerUp: (e: PointerEvent) => {
      const from = origin.current
      origin.current = null
      if (!from) return
      const dx = e.clientX - from.x
      const dy = e.clientY - from.y
      if (Math.abs(dx) < MIN_DISTANCE || Math.abs(dy) > MAX_OFF_AXIS) return
      onSwipe(dx < 0 ? 1 : -1)
    },
    onPointerCancel: () => {
      origin.current = null
    },
  }
}
