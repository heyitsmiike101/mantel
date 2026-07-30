import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { AppSettings, CalendarEvent, CalendarInfo, EventInput, User } from './types'

export function useUsers() {
  return useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/users') })
}

export function useCalendars() {
  return useQuery({ queryKey: ['calendars'], queryFn: () => api.get<CalendarInfo[]>('/calendars') })
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => api.get<AppSettings>('/settings') })
}

export function useEvents(start: Date, end: Date) {
  const s = start.toISOString()
  const e = end.toISOString()
  return useQuery({
    queryKey: ['events', s, e],
    queryFn: () =>
      api.get<CalendarEvent[]>(`/events?start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`),
  })
}

/** Everything that can change the calendar invalidates the same key, so every open
 *  screen converges on the next refetch. */
function useCalendarMutation<TVars, TData>(fn: (vars: TVars) => Promise<TData>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['events'] })
    },
  })
}

export const useCreateEvent = () =>
  useCalendarMutation((input: EventInput) => api.post<CalendarEvent>('/events', input))

export const useUpdateEvent = () =>
  useCalendarMutation(({ id, ...patch }: Partial<EventInput> & { id: number }) =>
    api.patch<CalendarEvent>(`/events/${id}`, patch),
  )

export const useDeleteEvent = () =>
  useCalendarMutation((id: number) => api.del<void>(`/events/${id}`))

export function useEntityMutation<TVars, TData>(fn: (v: TVars) => Promise<TData>, keys: string[]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => keys.forEach((k) => void qc.invalidateQueries({ queryKey: [k] })),
  })
}
