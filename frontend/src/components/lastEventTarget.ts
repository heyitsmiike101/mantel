import type { CalendarInfo } from '../api/types'

const STORAGE_KEY = 'mantel.lastEventTarget'

export interface EventTarget {
  profileId: number | null
  calendarId: number
}

/** Reads the remembered choice, tolerating anything at all in storage.
 *
 *  This is data a person can edit, that survives upgrades, and that a half-written
 *  value could be left in. Nothing here may throw -- the worst outcome allowed is
 *  "no memory", which just falls back to the normal default. */
export function parseTarget(raw: string | null): EventTarget | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw)
    if (typeof value !== 'object' || value === null) return null
    const { profileId, calendarId } = value as Record<string, unknown>
    if (typeof calendarId !== 'number') return null
    if (profileId !== null && typeof profileId !== 'number') return null
    return { profileId, calendarId }
  } catch {
    return null
  }
}

/** Is a remembered choice still true?
 *
 *  Calendars get unclaimed, reassigned, or switched off between one event and the
 *  next. Restoring a stale pair would either file the event somewhere unintended or
 *  show a profile whose calendar list no longer contains the selection. */
export function isStillValid(target: EventTarget, choices: CalendarInfo[]): boolean {
  const cal = choices.find((c) => c.id === target.calendarId)
  return !!cal && cal.claimed_by_user_id === target.profileId
}

export function readLastTarget(choices: CalendarInfo[]): EventTarget | null {
  let raw: string | null = null
  try {
    raw = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // private mode, or storage disabled
  }
  const target = parseTarget(raw)
  return target && isStillValid(target, choices) ? target : null
}

/** Remembered per device on purpose: the wall display in the kitchen files events
 *  differently from somebody's phone, and one shared server-side preference would
 *  have them overwriting each other. */
export function rememberLastTarget(profileId: number | null, calendarId: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ profileId, calendarId }))
  } catch {
    // Not being able to remember is not worth failing a save over.
  }
}
