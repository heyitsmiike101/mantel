import { useEffect, useState } from 'react'
import { useCalendars, useCreateEvent, useDeleteEvent, useUpdateEvent, useUsers } from '../api/hooks'
import type { CalendarEvent } from '../api/types'
import { calendarLabel, providerPossessive } from '../api/providers'
import { pickableCalendars } from './pickableCalendars'
import { calendarsForProfile, initialSelection, profilesWithCalendars } from './eventProfiles'
import { acquireReloadGuard } from '../hooks/useVersionPoll'
import { type Freq, RecurrencePicker, buildRule, parseRule } from './RecurrencePicker'

interface Props {
  event: CalendarEvent | null
  defaultStart: Date | null
  onClose: () => void
}

const HOUR_MS = 3_600_000

export function EventModal({ event, defaultStart, onClose }: Props) {
  const { data: calendars = [] } = useCalendars()
  const { data: users = [] } = useUsers()
  const create = useCreateEvent()
  const update = useUpdateEvent()
  const remove = useDeleteEvent()

  const isNew = event === null
  const readOnly = event !== null && !event.editable

  // Only calendars that can actually carry an event -- see pickableCalendars for why a
  // switched-off synced calendar would swallow one silently.
  const writable = pickableCalendars(calendars)
  const choices = isNew ? writable : pickableCalendars(calendars, event.calendar_id)

  const [title, setTitle] = useState(event?.title ?? '')
  const [location, setLocation] = useState(event?.location ?? '')
  const [description, setDescription] = useState(event?.description ?? '')
  const [allDay, setAllDay] = useState(event?.all_day ?? false)
  // Whose event is this? Chosen first, because it is the question somebody actually
  // has in mind -- the calendar is a consequence of it. Derived from the event's own
  // calendar when editing, so an existing event opens showing the truth.
  const start0 = initialSelection(choices, users, event?.calendar_id ?? null)
  const [profileId, setProfileId] = useState<number | null>(start0.profileId)
  const [calendarId, setCalendarId] = useState<number | null>(start0.calendarId)

  const profiles = profilesWithCalendars(choices, users)
  const profileCalendars = calendarsForProfile(choices, profileId)
  const [start, setStart] = useState(
    toLocalInput(event ? new Date(event.start_at) : (defaultStart ?? new Date())),
  )
  const [end, setEnd] = useState(
    toLocalInput(
      event
        ? new Date(event.end_at)
        : new Date((defaultStart ?? new Date()).getTime() + HOUR_MS),
    ),
  )
  const [error, setError] = useState<string | null>(null)
  const [repeat, setRepeat] = useState(() => parseRule(event?.recurrence_rule))

  useEffect(() => {
    // Calendars arrive after the first render, so the opening choice has to be made
    // again once they do.
    if (calendarId === null && choices.length > 0) {
      const pick = initialSelection(choices, users, event?.calendar_id ?? null)
      setProfileId(pick.profileId)
      setCalendarId(pick.calendarId)
    }
  }, [choices, users, calendarId, event])

  // Hold off the kiosk auto-reload while someone is mid-edit.
  useEffect(() => acquireReloadGuard(), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const busy = create.isPending || update.isPending || remove.isPending

  const submit = async () => {
    setError(null)
    if (!title.trim()) return setError('Give the event a title.')
    if (calendarId === null) return setError('No writable calendar available.')
    const startISO = allDay ? utcMidnight(start, 0) : new Date(start).toISOString()
    const endISO = allDay ? utcMidnight(end, 1) : new Date(end).toISOString()
    if (endISO <= startISO) return setError('The end time must be after the start time.')

    const body = {
      calendar_id: calendarId,
      title: title.trim(),
      location: location.trim() || null,
      description: description.trim() || null,
      start_at: startISO,
      end_at: endISO,
      all_day: allDay,
      recurrence_rule: buildRule(repeat.freq as Freq, repeat.byday, repeat.until),
    }
    try {
      if (isNew) await create.mutateAsync(body)
      else await update.mutateAsync({ id: event.id, ...body })
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the event.')
    }
  }

  const destroy = async () => {
    if (!event) return
    try {
      await remove.mutateAsync(event.id)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete the event.')
    }
  }

  return (
    <div className="modal" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal__card" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal__title">{isNew ? 'New event' : readOnly ? 'Event' : 'Edit event'}</h2>

        {readOnly && (
          <p className="modal__note">
            This calendar is read-only in{' '}
            {providerPossessive(calendars.find((c) => c.id === event.calendar_id)?.account_provider)}
            , so it can't be changed here.
          </p>
        )}

        {event?.recurring && !event.recurrence_rule && (
          <p className="modal__note">
            This is one occurrence of a repeating event. Changes apply to this occurrence only.
          </p>
        )}
        {event?.recurrence_text && (
          <p className="modal__note">{event.recurrence_text}</p>
        )}

        <label className="field">
          <span>Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={readOnly}
            autoFocus={isNew}
            placeholder="Soccer practice"
          />
        </label>

        <label className="field">
          <span>Who is this for?</span>
          <select
            value={profileId ?? ''}
            onChange={(e) => {
              const next = e.target.value === '' ? null : Number(e.target.value)
              setProfileId(next)
              // Their calendars are a different set, so the old choice may not be in
              // it. Land on their first one rather than leaving a stale selection.
              setCalendarId(calendarsForProfile(choices, next)[0]?.id ?? null)
            }}
            disabled={readOnly || !isNew}
          >
            {profiles.map((p) => (
              <option key={p.id ?? 'household'} value={p.id ?? ''}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Calendar</span>
          <select
            value={calendarId ?? ''}
            onChange={(e) => setCalendarId(Number(e.target.value))}
            disabled={readOnly || !isNew}
          >
            {profileCalendars.map((c) => (
              <option key={c.id} value={c.id}>
                {calendarLabel(c)}
              </option>
            ))}
          </select>
        </label>

        <div className="field field--row">
          <label className="field">
            <span>Starts</span>
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              disabled={readOnly}
            />
          </label>
          <label className="field">
            <span>Ends</span>
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              disabled={readOnly}
            />
          </label>
        </div>

        <RecurrencePicker
          freq={repeat.freq}
          byday={repeat.byday}
          until={repeat.until}
          start={new Date(start)}
          disabled={readOnly}
          onChange={setRepeat}
        />

        <button
          className={`toggle ${allDay ? 'toggle--on' : ''}`}
          onClick={() => !readOnly && setAllDay(!allDay)}
          disabled={readOnly}
        >
          {allDay ? '☑' : '☐'} All day
        </button>

        <label className="field">
          <span>Location</span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            disabled={readOnly}
            placeholder="Riverside Park"
          />
        </label>

        <label className="field">
          <span>Notes</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={readOnly}
            rows={2}
          />
        </label>

        {error && <p className="modal__error">{error}</p>}

        <div className="modal__actions">
          {!isNew && !readOnly && (
            <button className="btn btn--danger" onClick={destroy} disabled={busy}>
              Delete
            </button>
          )}
          <div className="modal__spacer" />
          <button className="btn" onClick={onClose} disabled={busy}>
            {readOnly ? 'Close' : 'Cancel'}
          </button>
          {!readOnly && (
            <button className="btn btn--primary" onClick={submit} disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** All-day events mean whole calendar dates, so they are stored on UTC midnight
 *  boundaries with an exclusive end -- never shifted by the viewer's timezone. */
function utcMidnight(localInput: string, addDays: number): string {
  const [y, m, d] = localInput.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + addDays)).toISOString()
}

/** <input type="datetime-local"> wants wall-clock local time with no offset. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
