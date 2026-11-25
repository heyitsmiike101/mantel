import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { useCalendars } from '../../api/hooks'
import type { CalendarInfo } from '../../api/types'
import { BackupsTab, RestoreConfirmation, restoreDestinations, restoreSnapshot } from './BackupsTab'

vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn() }))
vi.mock('../../api/hooks', () => ({ useCalendars: vi.fn(), useEntityMutation: vi.fn(() => ({ isPending: false })) }))
vi.mock('../../api/client', () => ({ api: { post: vi.fn() } }))

const calendar = (id: number, overrides: Partial<CalendarInfo> = {}): CalendarInfo => ({
  id,
  name: `Calendar ${id}`,
  is_local: false,
  google_calendar_id: null,
  linked_account_id: 1,
  account_email: null,
  account_provider: 'google',
  claimed_by_user_id: 1,
  color: '#fff',
  sync_enabled: true,
  access_role: 'owner',
  writable: true,
  last_synced_at: null,
  sync_error: null,
  ...overrides,
})

const snapshot = {
  id: 12,
  event_id: 9,
  calendar_id: 1,
  calendar_name: 'Old family calendar',
  calendar_source: 'google',
  calendar_created_at: '2026-01-01T12:00:00Z',
  action: 'deleted',
  recorded_at: '2026-11-12T15:00:00Z',
  title: 'Dentist',
  description: null,
  location: null,
  start_at: '2026-12-01T15:00:00Z',
  end_at: '2026-12-01T16:00:00Z',
  all_day: false,
  timezone: null,
  recurrence_rule: null,
  exdates: null,
  status: 'confirmed',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useCalendars).mockReturnValue({ data: [calendar(1)] } as ReturnType<typeof useCalendars>)
})

describe('event backups', () => {
  it('lists snapshots with title, action, prior calendar, saved time, event time and paging', () => {
    vi.mocked(useQuery).mockReturnValue({ data: { items: [snapshot], total: 27, limit: 20, offset: 0 } } as ReturnType<typeof useQuery>)
    const html = renderToStaticMarkup(<BackupsTab />)
    expect(html).toContain('Dentist')
    expect(html).toContain('deleted')
    expect(html).toContain('Previously in Old family calendar · Saved')
    expect(html).toContain('Event:')
    expect(html).toContain('Showing 1–1 of 27 backups')
    expect(html).toContain('>Next</button>')
    expect(html).toContain('aria-expanded="false"')
    expect(vi.mocked(useQuery).mock.calls[0][0].queryKey).toEqual(['event-history', 0])
  })

  it('shows an empty state and a loading failure', () => {
    vi.mocked(useQuery).mockReturnValue({ data: { items: [], total: 0, limit: 20, offset: 0 } } as ReturnType<typeof useQuery>)
    expect(renderToStaticMarkup(<BackupsTab />)).toContain('No event backups yet')
    vi.mocked(useQuery).mockReturnValue({ isError: true, error: new Error('Network offline') } as ReturnType<typeof useQuery>)
    expect(renderToStaticMarkup(<BackupsTab />)).toContain('Network offline')
  })

  it('offers only writable and syncing destinations, including local calendars', () => {
    expect(restoreDestinations([
      calendar(1, { writable: false }),
      calendar(2, { sync_enabled: false }),
      calendar(3, { is_local: true, sync_enabled: false }),
      calendar(4),
    ]).map((cal) => cal.id)).toEqual([3, 4])
  })

  it('requires a destination if the original is missing, and explains the copy is non-destructive', () => {
    const html = renderToStaticMarkup(<RestoreConfirmation
      item={snapshot} destinations={[calendar(2)]} destination="" loading={false}
      calendarError={false} pending={false} onDestinationChange={() => {}} onConfirm={() => {}}
    />)
    expect(html).toContain('Choose a destination')
    expect(html).toContain('original calendar is unavailable')
    expect(html).toContain('does not remove or replace any moved or current event')
    expect(html).toMatch(/disabled=""[^>]*>Confirm restore copy/)
    expect(html).toContain('value="2"')
  })

  it('allows an eligible original and handles no writable calendars', () => {
    const render = (destinations: CalendarInfo[]) => renderToStaticMarkup(<RestoreConfirmation
      item={snapshot} destinations={destinations} destination="" loading={false}
      calendarError={false} pending={false} onDestinationChange={() => {}} onConfirm={() => {}}
    />)
    expect(render([calendar(1)])).toContain('Original: Calendar 1')
    expect(render([])).toContain('No writable calendars are available')
  })

  it('sends an empty payload for original restore and an explicit destination for another calendar', async () => {
    vi.mocked(api.post).mockResolvedValue({ id: 50 })
    await restoreSnapshot(12)
    await restoreSnapshot(12, 2)
    expect(api.post).toHaveBeenNthCalledWith(1, '/events/history/12/restore', {})
    expect(api.post).toHaveBeenNthCalledWith(2, '/events/history/12/restore', { calendar_id: 2 })
  })
})
