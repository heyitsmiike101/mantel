import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEntityMutation, useEvents } from './hooks'

vi.mock('@tanstack/react-query', () => ({
  useMutation: vi.fn(),
  useQuery: vi.fn(),
  useQueryClient: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('remote calendar refresh', () => {
  it('polls active event queries so events created on a phone appear without navigation', () => {
    function Events() {
      useEvents(new Date('2026-11-01T00:00:00Z'), new Date('2026-12-01T00:00:00Z'))
      return null
    }

    renderToStaticMarkup(<Events />)
    expect(vi.mocked(useQuery).mock.calls[0][0]).toMatchObject({
      queryKey: ['events', '2026-11-01T00:00:00.000Z', '2026-12-01T00:00:00.000Z', ''],
      refetchInterval: 60_000,
    })
  })

  it('invalidates all event windows and newly discovered calendars after a successful sync', () => {
    const invalidateQueries = vi.fn()
    vi.mocked(useQueryClient).mockReturnValue({ invalidateQueries } as unknown as ReturnType<typeof useQueryClient>)

    function Sync() {
      useEntityMutation(() => Promise.resolve(), ['events', 'calendars', 'sync-status', 'accounts'])
      return null
    }

    renderToStaticMarkup(<Sync />)
    const options = vi.mocked(useMutation).mock.calls[0][0]
    expect(options).toBeDefined()
    if (!options || typeof options !== 'object' || !('onSuccess' in options)) return
    options.onSuccess?.(undefined, undefined, undefined, { client: {} as never, meta: undefined, mutationKey: undefined })
    expect(invalidateQueries.mock.calls.map(([arg]) => arg.queryKey)).toEqual([
      ['events'], ['calendars'], ['sync-status'], ['accounts'],
    ])
  })
})
