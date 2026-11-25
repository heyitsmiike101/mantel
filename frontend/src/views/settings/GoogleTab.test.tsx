import { useQuery } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useEntityMutation, useSettings, useUsers } from '../../api/hooks'
import { GoogleTab } from './GoogleTab'

vi.mock('@tanstack/react-query', () => ({ useQuery: vi.fn() }))
vi.mock('../../api/hooks', () => ({
  useSettings: vi.fn(),
  useUsers: vi.fn(),
  useEntityMutation: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('window', { location: { search: '', origin: 'http://localhost:8080' } })
  vi.mocked(useSettings).mockReturnValue({
    data: {
      server: { google_configured: true, google_client_secret_set: true },
      public_base_url: 'http://localhost:8080',
      google_client_id: 'client-id',
    },
  } as ReturnType<typeof useSettings>)
  vi.mocked(useUsers).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useUsers>)
  vi.mocked(useQuery)
    .mockReturnValueOnce({ data: [] } as unknown as ReturnType<typeof useQuery>)
    .mockReturnValueOnce({ data: { interval_seconds: 300, pending_pushes: 0 } } as ReturnType<typeof useQuery>)
  vi.mocked(useEntityMutation).mockReturnValue({ isPending: false, mutate: vi.fn() } as unknown as ReturnType<typeof useEntityMutation>)
})

describe('Google sync', () => {
  it('refreshes event windows and calendar assignments as well as status and accounts', () => {
    const html = renderToStaticMarkup(<GoogleTab />)

    expect(html).toContain('Sync now')
    expect(vi.mocked(useEntityMutation).mock.calls[2][1]).toEqual([
      'events', 'calendars', 'sync-status', 'accounts',
    ])
  })
})
