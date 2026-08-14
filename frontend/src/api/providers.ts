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

/** A calendar's name for a picker: "Family (Apple · you@example.com)".
 *
 *  The address alone is not enough to tell two calendars apart. An Apple ID is very
 *  often a gmail address, so somebody who links both services ends up with two
 *  accounts under an identical email -- and the new-event picker offered
 *  "Family (you@gmail.com)" twice, with no way to know which service an event was
 *  about to be saved to. On that screen, guessing wrong files the event somewhere
 *  nobody is looking.
 */
export function calendarLabel(c: {
  name: string
  account_provider?: string | null
  account_email?: string | null
}): string {
  if (!c.account_provider && !c.account_email) return c.name
  const source = c.account_provider ? providerLabel(c.account_provider) : null

  // A primary calendar is named after the account, so the full form says the same
  // address twice: "mfuentes@realestatefuentes.com (Google · mfuentes@realestate…)"
  // -- 72 characters to convey about 35, in a dropdown 276px wide on a phone. The
  // service alone is the only part that adds anything.
  const sameAsName = !!c.account_email && c.account_email === c.name
  const parts = sameAsName ? [source] : [source, c.account_email]

  return `${c.name} (${parts.filter(Boolean).join(' · ')})`
}
