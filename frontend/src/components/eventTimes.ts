/** Where the end time should land when the start moves.
 *
 *  Two behaviours, and which applies depends on whether anybody has actually chosen
 *  an end:
 *
 *  - Nobody has: the end follows the start, 30 minutes later. Setting a start and
 *    getting a sensible end for free is the whole point -- an end left where it was
 *    is either wrong or, if the start moved past it, invalid.
 *  - Somebody has: the length they chose is kept and the whole event moves. Deciding
 *    an event runs two hours and then having that silently cut to 30 minutes because
 *    the start was corrected would be worse than not helping at all.
 *
 *  Values are `datetime-local` strings and stay in that form.
 */
export function endFor(
  nextStart: string,
  previousStart: string,
  currentEnd: string,
  endEdited: boolean,
): string {
  const next = parseLocal(nextStart)
  if (!next) return currentEnd // mid-typing; leave it alone

  if (!endEdited) return toLocalInput(new Date(next.getTime() + DEFAULT_MINUTES * 60_000))

  const before = parseLocal(previousStart)
  const end = parseLocal(currentEnd)
  if (!before || !end) return currentEnd

  // Keep the length they chose, so the event moves rather than being reshaped. A
  // negative duration -- an end already before its start -- is clamped, or moving the
  // start would carry that mistake along with it.
  const duration = Math.max(end.getTime() - before.getTime(), DEFAULT_MINUTES * 60_000)
  return toLocalInput(new Date(next.getTime() + duration))
}

export const DEFAULT_MINUTES = 30

/** A `datetime-local` value, or null if it isn't a complete one yet.
 *
 *  `new Date()` must not be trusted to decide that. It reads "2026-08-" -- which is
 *  what the field holds part-way through typing a date -- as the 1st of August rather
 *  than as nonsense, so a half-typed start would quietly move the end to a date
 *  nobody chose. Only a fully-formed value is accepted. */
function parseLocal(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** The format `<input type="datetime-local">` expects, in local time. */
export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`
}
