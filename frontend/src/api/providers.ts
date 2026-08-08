/** What to call a calendar's source in front of a person.
 *
 *  The app speaks to two services with very different names for themselves: the API
 *  says `google` and `icloud`, but nobody calls it iCloud Calendar in the Apple UI --
 *  it's "Apple Calendar", or just Calendar. Kept in one place so a calendar that came
 *  from an iPhone is never labelled Google somewhere the wording was written before
 *  there was a second provider.
 *
 *  `null` is a calendar that lives only in this app; 'Synced' is the honest answer for
 *  a provider added later that this build doesn't know about yet.
 */
export function providerLabel(provider: string | null | undefined): string {
  if (provider === 'icloud') return 'Apple'
  if (provider === 'google') return 'Google'
  return 'Synced'
}

/** "read-only in Apple Calendar" / "read-only in Google" — the phrase that tells
 *  somebody where to go and change it, since they can't change it here. */
export function providerPossessive(provider: string | null | undefined): string {
  if (provider === 'icloud') return 'Apple Calendar'
  if (provider === 'google') return 'Google'
  return 'the service it came from'
}
