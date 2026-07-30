import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'famcal.personFilter'

function read(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((v) => typeof v === 'number') : []
  } catch {
    return []
  }
}

/**
 * Which family members' events to show. An empty list means everyone.
 *
 * Kept in localStorage rather than the shared settings table on purpose: the wall
 * display in the kitchen and a phone in someone's pocket want different filters,
 * and a filter is a view preference, not household configuration.
 */
export function usePersonFilter() {
  const [userIds, setUserIds] = useState<number[]>(read)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(userIds))
    } catch {
      /* private browsing or a full quota; the filter just won't persist */
    }
  }, [userIds])

  const toggle = useCallback((id: number) => {
    setUserIds((current) =>
      current.includes(id) ? current.filter((v) => v !== id) : [...current, id],
    )
  }, [])

  const clear = useCallback(() => setUserIds([]), [])

  return { userIds, toggle, clear, showingEveryone: userIds.length === 0 }
}
