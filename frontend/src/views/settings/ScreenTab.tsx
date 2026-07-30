import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api } from '../../api/client'
import { useEntityMutation, useSettings } from '../../api/hooks'
import type { AppSettings, Photo } from '../../api/types'

export function ScreenTab() {
  const { data: settings } = useSettings()
  const save = useEntityMutation(
    (patch: Partial<AppSettings>) => api.patch<AppSettings>('/settings', patch),
    ['settings'],
  )

  if (!settings) return null

  return (
    <section className="panel">
      <h2>Screensaver</h2>
      <p className="hint">
        What a wall display shows when nobody has touched it for a while. Touch the screen to
        bring the calendar back.
      </p>

      <div className="row">
        <div className="row__name row__name--static">Screensaver</div>
        {(
          [
            ['auto', 'Photos, else clock'],
            ['photos', 'Photos only'],
            ['clock', 'Clock only'],
            ['off', 'Off'],
          ] as const
        ).map(([v, label]) => (
          <button
            key={v}
            className="btn"
            aria-current={settings.screensaver_mode === v ? 'page' : undefined}
            onClick={() => save.mutate({ screensaver_mode: v })}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="row__name row__name--static">Starts after</div>
        <select
          value={settings.screensaver_delay_minutes}
          onChange={(e) => save.mutate({ screensaver_delay_minutes: Number(e.target.value) })}
        >
          {[1, 2, 3, 5, 10, 15, 30, 60].map((m) => (
            <option key={m} value={m}>
              {m} minute{m === 1 ? '' : 's'}
            </option>
          ))}
        </select>
      </div>

      <div className="row">
        <div className="row__name row__name--static">Seconds per photo</div>
        <select
          value={settings.screensaver_seconds_per_photo}
          onChange={(e) =>
            save.mutate({ screensaver_seconds_per_photo: Number(e.target.value) })
          }
        >
          {[5, 10, 20, 30, 60, 120].map((s) => (
            <option key={s} value={s}>
              {s} seconds
            </option>
          ))}
        </select>
        <button
          className="btn"
          aria-current={settings.screensaver_shuffle ? 'page' : undefined}
          onClick={() => save.mutate({ screensaver_shuffle: !settings.screensaver_shuffle })}
        >
          {settings.screensaver_shuffle ? '☑' : '☐'} Shuffle
        </button>
      </div>

      <h2 style={{ marginTop: 24 }}>Overnight</h2>
      <p className="hint">
        Blanks the page during the hours nobody is up. A browser can't switch the panel's
        backlight off — for that, see the screen-power section of the kiosk setup guide.
      </p>

      <div className="row">
        <div className="row__name row__name--static">Dark overnight</div>
        <button
          className="btn"
          aria-current={settings.sleep_enabled ? 'page' : undefined}
          onClick={() => save.mutate({ sleep_enabled: !settings.sleep_enabled })}
        >
          {settings.sleep_enabled ? '☑ On' : '☐ Off'}
        </button>
        <select
          value={settings.sleep_start_hour}
          onChange={(e) => save.mutate({ sleep_start_hour: Number(e.target.value) })}
          disabled={!settings.sleep_enabled}
        >
          {hours().map((h) => (
            <option key={h} value={h}>
              from {formatHour(h)}
            </option>
          ))}
        </select>
        <select
          value={settings.sleep_end_hour}
          onChange={(e) => save.mutate({ sleep_end_hour: Number(e.target.value) })}
          disabled={!settings.sleep_enabled}
        >
          {hours().map((h) => (
            <option key={h} value={h}>
              until {formatHour(h)}
            </option>
          ))}
        </select>
      </div>

      <div className="row">
        <div className="row__name row__name--static">
          Burn-in protection
          <div className="hint">Nudges the layout a few pixels every 10 minutes.</div>
        </div>
        <button
          className="btn"
          aria-current={settings.burn_in_shift ? 'page' : undefined}
          onClick={() => save.mutate({ burn_in_shift: !settings.burn_in_shift })}
        >
          {settings.burn_in_shift ? '☑ On' : '☐ Off'}
        </button>
      </div>

      <h2 style={{ marginTop: 24 }}>Photos</h2>
      <PhotoLibrary />
    </section>
  )
}

function PhotoLibrary() {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: photos = [] } = useQuery({
    queryKey: ['photos'],
    queryFn: () => api.get<Photo[]>('/photos'),
  })

  const remove = useEntityMutation((id: number) => api.del<void>(`/photos/${id}`), ['photos'])

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setBusy(true)
    setError(null)
    const failures: string[] = []

    for (const file of Array.from(files)) {
      const body = new FormData()
      body.append('file', file)
      // Not the shared api client: this is multipart, and setting a JSON
      // Content-Type here would strip the multipart boundary.
      const res = await fetch('/api/photos', { method: 'POST', body })
      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        failures.push(`${file.name}: ${detail?.error?.message ?? res.statusText}`)
      }
    }

    if (failures.length) setError(failures.join(' · '))
    await qc.invalidateQueries({ queryKey: ['photos'] })
    setBusy(false)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <>
      <p className="hint">
        JPEG, PNG or WebP. Photos are resized and their location data is removed before being
        saved. They live in the same volume as your calendar, so your backup already covers them.
      </p>

      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          void upload(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          hidden
          onChange={(e) => void upload(e.target.files)}
        />
        {busy ? 'Uploading…' : 'Drop photos here, or tap to choose'}
      </div>

      {error && <p className="banner banner--warn">{error}</p>}

      {photos.length === 0 ? (
        <p className="hint">
          No photos yet — the screensaver will show a clock and today's schedule instead.
        </p>
      ) : (
        <div className="photogrid">
          {photos.map((p) => (
            <figure key={p.id} className="photogrid__item">
              <img src={p.url} alt={p.original_name ?? ''} loading="lazy" />
              <button
                className="photogrid__remove"
                aria-label={`Delete ${p.original_name ?? 'photo'}`}
                onClick={() => remove.mutate(p.id)}
              >
                ✕
              </button>
            </figure>
          ))}
        </div>
      )}
    </>
  )
}

function hours(): number[] {
  return Array.from({ length: 24 }, (_, i) => i)
}

function formatHour(h: number): string {
  const suffix = h < 12 ? 'am' : 'pm'
  const display = h % 12 === 0 ? 12 : h % 12
  return `${display}${suffix}`
}
