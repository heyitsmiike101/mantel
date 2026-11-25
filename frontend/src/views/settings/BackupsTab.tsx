import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { useCalendars, useEntityMutation } from '../../api/hooks'
import type { CalendarEvent, CalendarInfo } from '../../api/types'
import { pickableCalendars } from '../../components/pickableCalendars'

interface EventHistory {
  id: number
  event_id: number
  calendar_id: number
  calendar_name: string
  calendar_source: string
  calendar_created_at: string
  action: string
  recorded_at: string
  title: string
  description: string | null
  location: string | null
  start_at: string
  end_at: string
  all_day: boolean
  timezone: string | null
  recurrence_rule: string | null
  exdates: string | null
  status: string
}

interface HistoryPage {
  items: EventHistory[]
  total: number
  limit: number
  offset: number
}

const PAGE_SIZE = 20

export function restoreDestinations(calendars: CalendarInfo[]): CalendarInfo[] {
  return pickableCalendars(calendars)
}

function dateLabel(value: string, allDay = false): string {
  const date = allDay ? new Date(`${value.slice(0, 10)}T12:00:00`) : new Date(value)
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    ...(allDay ? {} : { timeStyle: 'short' }),
  }).format(date)
}

export function restoreSnapshot(id: number, calendarId?: number): Promise<CalendarEvent> {
  return api.post<CalendarEvent>(`/events/history/${id}/restore`, calendarId === undefined ? {} : { calendar_id: calendarId })
}

export function BackupsTab() {
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [destination, setDestination] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const history = useQuery({
    queryKey: ['event-history', offset],
    queryFn: () => api.get<HistoryPage>(`/events/history?limit=${PAGE_SIZE}&offset=${offset}`),
  })
  const calendars = useCalendars()
  const destinations = restoreDestinations(calendars.data ?? [])
  const restore = useEntityMutation(
    ({ id, calendarId }: { id: number; calendarId?: number }) => restoreSnapshot(id, calendarId),
    ['events', 'event-history'],
  )
  const total = history.data?.total ?? 0
  const current = history.data?.items.find((item) => item.id === selected)
  const original = current && destinations.find((cal) => cal.id === current.calendar_id)
  const targetId = destination ? Number(destination) : original?.id
  const target = destinations.find((cal) => cal.id === targetId)

  async function confirmRestore() {
    if (!current || !target || restore.isPending) return
    setError(null)
    setSuccess(null)
    try {
      await restore.mutateAsync({ id: current.id, calendarId: destination ? target.id : undefined })
      setSuccess(`Restored “${current.title}” as a new event in ${target.name}.`)
      setSelected(null)
      setDestination('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not restore this event.')
    }
  }

  return (
    <section className="panel backups">
      <h2>Event backups</h2>
      <p className="hint">Browse saved versions of events and restore a copy when you need one.</p>
      {error && <p className="banner banner--warn" role="alert">{error}</p>}
      {success && <p className="banner" role="status">{success}</p>}
      {history.isPending && <p role="status">Loading backups…</p>}
      {history.isError && (
        <p className="banner banner--warn" role="alert">
          {history.error instanceof Error ? history.error.message : 'Could not load backups.'}
          <button className="btn" onClick={() => void history.refetch()}>Try again</button>
        </p>
      )}
      {history.data && history.data.items.length === 0 && (
        <p className="hint">
          {offset === 0 ? 'No event backups yet. Changes and deletions will appear here.' : 'No backups on this page.'}
        </p>
      )}
      {history.data && history.data.items.length > 0 && (
        <>
          <ul className="backups__list">
            {history.data.items.map((item) => (
              <li key={item.id} className="backups__item">
                <div className="backups__details">
                  <div className="backups__heading">
                    <strong>{item.title}</strong>
                    <span className="backups__action">{item.action.replaceAll('_', ' ')}</span>
                  </div>
                  <span>Previously in {item.calendar_name} · Saved {dateLabel(item.recorded_at)}</span>
                  <span>Event: {dateLabel(item.start_at, item.all_day)}{item.all_day ? ' · All day' : ''}</span>
                </div>
                <button
                  className="btn"
                  aria-expanded={selected === item.id}
                  onClick={() => {
                    setSelected(selected === item.id ? null : item.id)
                    setDestination('')
                    setError(null)
                    setSuccess(null)
                  }}
                >
                  {selected === item.id ? 'Cancel' : 'Restore copy'}
                </button>
                {selected === item.id && (
                  <RestoreConfirmation
                    item={item}
                    destinations={destinations}
                    destination={destination}
                    loading={calendars.isPending}
                    calendarError={calendars.isError}
                    pending={restore.isPending}
                    onDestinationChange={setDestination}
                    onConfirm={() => void confirmRestore()}
                  />
                )}
              </li>
            ))}
          </ul>
          <div className="backups__pagination">
            <span>Showing {offset + 1}–{offset + history.data.items.length} of {total} backups</span>
            <div>
              <button className="btn" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setSelected(null); setError(null) }}>Previous</button>
              <button className="btn" disabled={offset + PAGE_SIZE >= total} onClick={() => { setOffset(offset + PAGE_SIZE); setSelected(null); setError(null) }}>Next</button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

interface RestoreConfirmationProps {
  item: EventHistory
  destinations: CalendarInfo[]
  destination: string
  loading: boolean
  calendarError: boolean
  pending: boolean
  onDestinationChange: (id: string) => void
  onConfirm: () => void
}

export function RestoreConfirmation({ item, destinations, destination, loading, calendarError, pending, onDestinationChange, onConfirm }: RestoreConfirmationProps) {
  const original = destinations.find((cal) => cal.id === item.calendar_id)
  const target = destination ? destinations.find((cal) => cal.id === Number(destination)) : original

  return (
    <div className="backups__confirm">
      <label htmlFor={`backup-destination-${item.id}`}>Restore into calendar</label>
      <select
        id={`backup-destination-${item.id}`}
        value={destination}
        disabled={loading || pending || calendarError}
        onChange={(e) => onDestinationChange(e.target.value)}
      >
        {original ? <option value="">Original: {original.name}</option> : <option value="">Choose a destination</option>}
        {destinations.filter((cal) => cal.id !== original?.id).map((cal) => (
          <option key={cal.id} value={cal.id}>{cal.name}</option>
        ))}
      </select>
      {!original && <p className="hint">The original calendar is unavailable or not writable. Choose another calendar.</p>}
      {calendarError && <p className="banner banner--warn" role="alert">Could not load available calendars.</p>}
      {!loading && !calendarError && destinations.length === 0 && (
        <p className="hint">No writable calendars are available. Enable syncing on a writable calendar or add a local calendar.</p>
      )}
      <p>Restoring creates a new copy. It does not remove or replace any moved or current event.</p>
      <button className="btn btn--primary" disabled={!target || pending || calendarError} onClick={onConfirm}>
        {pending ? 'Restoring…' : 'Confirm restore copy'}
      </button>
    </div>
  )
}
