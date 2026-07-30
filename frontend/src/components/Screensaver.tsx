import { useQuery } from '@tanstack/react-query'
import { addDays, format } from 'date-fns'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useEvents, useSettings } from '../api/hooks'
import type { Photo } from '../api/types'
import { useIdle, useSleepWindow } from '../hooks/useIdle'

/**
 * The idle state of a wall display. Either a photo slideshow or a big clock with
 * today's remaining schedule -- the thing a family glances at from the doorway.
 *
 * Deliberately covers the whole viewport and swallows the first tap: waking a
 * screen should never also press a button underneath it.
 */
export function Screensaver() {
  const { data: settings } = useSettings()

  const enabled = settings?.screensaver_enabled ?? false
  const mode = settings?.screensaver_mode ?? 'auto'
  const delayMs = (settings?.screensaver_delay_minutes ?? 5) * 60_000

  const idle = useIdle(delayMs, enabled && mode !== 'off')
  const asleep = useSleepWindow(
    settings?.sleep_enabled ?? false,
    settings?.sleep_start_hour ?? 23,
    settings?.sleep_end_hour ?? 7,
  )

  const { data: photos = [] } = useQuery({
    queryKey: ['photos'],
    queryFn: () => api.get<Photo[]>('/photos'),
    enabled: mode !== 'clock',
  })

  const showing = asleep || idle
  const usePhotos = mode !== 'clock' && photos.length > 0

  // Any interaction dismisses it; the capture-phase handler stops that same
  // interaction reaching the app underneath.
  const dismiss = (e: React.SyntheticEvent) => {
    e.stopPropagation()
    e.preventDefault()
    window.dispatchEvent(new Event('pointerdown'))
  }

  if (!showing) return null

  if (asleep) {
    return (
      <div className="saver saver--sleep" onPointerDownCapture={dismiss} role="presentation">
        <SleepClock />
      </div>
    )
  }

  return (
    <div className="saver" onPointerDownCapture={dismiss} role="presentation">
      {usePhotos ? (
        <PhotoSlideshow
          photos={photos}
          shuffle={settings?.screensaver_shuffle ?? true}
          seconds={settings?.screensaver_seconds_per_photo ?? 20}
        />
      ) : (
        <ClockScreen />
      )}
    </div>
  )
}

function PhotoSlideshow({
  photos,
  shuffle,
  seconds,
}: {
  photos: Photo[]
  shuffle: boolean
  seconds: number
}) {
  const [order] = useState(() => (shuffle ? shuffled(photos) : photos))
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (order.length <= 1) return
    const timer = setInterval(() => setIndex((i) => (i + 1) % order.length), seconds * 1000)
    return () => clearInterval(timer)
  }, [order.length, seconds])

  const current = order[index]
  const next = order[(index + 1) % order.length]

  return (
    <>
      {/* The next image is mounted hidden so it is already decoded when its turn
          comes -- otherwise every transition flashes a blank frame. */}
      {next && next.id !== current?.id && (
        <img className="saver__preload" src={next.url} alt="" aria-hidden />
      )}
      {current && <img key={current.id} className="saver__photo" src={current.url} alt="" />}
      <div className="saver__overlay">
        <ClockOverlay />
      </div>
    </>
  )
}

function ClockScreen() {
  const now = useNow(20_000)
  const dayStart = new Date(now)
  dayStart.setHours(0, 0, 0, 0)
  const { data: events = [] } = useEvents(dayStart, addDays(dayStart, 1))
  const remaining = events.filter((e) => new Date(e.end_at) > now).slice(0, 6)

  return (
    <div className="saver__clockscreen">
      <div className="saver__time">{format(now, 'h:mm')}</div>
      <div className="saver__date">{format(now, 'EEEE, MMMM d')}</div>
      {remaining.length > 0 && (
        <ul className="saver__agenda">
          {remaining.map((e) => (
            <li key={e.id}>
              <span className="saver__dot" style={{ background: e.color }} />
              <span className="saver__agenda-time">
                {e.all_day ? 'All day' : format(new Date(e.start_at), 'h:mm a')}
              </span>
              <span className="saver__agenda-title">{e.title}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ClockOverlay() {
  const now = useNow(20_000)
  return (
    <>
      <div className="saver__overlay-time">{format(now, 'h:mm')}</div>
      <div className="saver__overlay-date">{format(now, 'EEEE, MMMM d')}</div>
    </>
  )
}

/** Dim clock for the overnight window -- enough to read at 3am, not enough to light a room. */
function SleepClock() {
  const now = useNow(30_000)
  return <div className="saver__sleeptime">{format(now, 'h:mm')}</div>
}

function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}

function shuffled<T>(items: T[]): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}
