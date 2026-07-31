import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'famcal.hiddenPeople'

/** Parse whatever is in storage, tolerating anything that isn't a list of ids. */
export function parseHidden(raw: string | null): number[] {
  try {
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((v) => typeof v === 'number') : []
  } catch {
    return []
  }
}

export function toggleId(hidden: number[], id: number): number[] {
  return hidden.includes(id) ? hidden.filter((v) => v !== id) : [...hidden, id]
}

/**
 * Events on a calendar nobody has claimed have no owner and always show -- they
 * belong to the household rather than to a person, so hiding everybody must not
 * make the shared "Family" calendar disappear too.
 */
export function isPersonVisible(hidden: number[], userId: number | null | undefined): boolean {
  if (userId === null || userId === undefined) return true
  return !hidden.includes(userId)
}

/**
 * Which family members are hidden from the calendar.
 *
 * Hidden ids are stored rather than visible ones, deliberately: everyone should
 * be on screen by default, and someone added to the family later must appear
 * without anybody having to go and tick them on.
 *
 * Kept in localStorage rather than the shared settings table, because the wall
 * display in the kitchen and a phone in someone's pocket want different views.
 * It is a way of looking at the calendar, not household configuration.
 */
export function usePersonFilter() {
  const [hiddenUserIds, setHidden] = useState<number[]>(() =>
    parseHidden(safeRead(STORAGE_KEY)),
  )

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(hiddenUserIds))
    } catch {
      /* private browsing or a full quota; the choice just won't persist */
    }
  }, [hiddenUserIds])

  const toggle = useCallback((id: number) => setHidden((cur) => toggleId(cur, id)), [])
  const showEveryone = useCallback(() => setHidden([]), [])
  const isVisible = useCallback(
    (userId: number | null | undefined) => isPersonVisible(hiddenUserIds, userId),
    [hiddenUserIds],
  )

  return {
    hiddenUserIds,
    toggle,
    showEveryone,
    isVisible,
    anyHidden: hiddenUserIds.length > 0,
  }
}

function safeRead(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
