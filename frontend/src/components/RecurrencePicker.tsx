import { format } from 'date-fns'

const DAY_CODES = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'] as const
const DAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'] as const

export type Freq = 'NONE' | 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY'

/** Reads an RRULE back into the picker's controls. */
export function parseRule(rule: string | null | undefined): {
  freq: Freq
  byday: string[]
  until: string
} {
  if (!rule) return { freq: 'NONE', byday: [], until: '' }
  const parts = Object.fromEntries(
    rule
      .split(';')
      .filter((p) => p.includes('='))
      .map((p) => p.split('=', 2) as [string, string]),
  )
  const freq = (parts.FREQ as Freq) ?? 'NONE'
  const raw = parts.UNTIL ?? ''
  return {
    freq: (['DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'] as string[]).includes(freq) ? freq : 'NONE',
    byday: parts.BYDAY ? parts.BYDAY.split(',') : [],
    // UNTIL is a compact iCalendar stamp; the date input wants YYYY-MM-DD.
    until: raw.length >= 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : '',
  }
}

export function buildRule(freq: Freq, byday: string[], until: string): string | null {
  if (freq === 'NONE') return null
  const parts = [`FREQ=${freq}`]
  if (freq === 'WEEKLY' && byday.length) parts.push(`BYDAY=${byday.join(',')}`)
  if (until) parts.push(`UNTIL=${until.replaceAll('-', '')}T235959`)
  return parts.join(';')
}

interface Props {
  freq: Freq
  byday: string[]
  until: string
  start: Date
  disabled?: boolean
  onChange: (next: { freq: Freq; byday: string[]; until: string }) => void
}

export function RecurrencePicker({ freq, byday, until, start, disabled, onChange }: Props) {
  const options: [Freq, string][] = [
    ['NONE', 'Once'],
    ['DAILY', 'Daily'],
    ['WEEKLY', 'Weekly'],
    ['MONTHLY', 'Monthly'],
    ['YEARLY', 'Yearly'],
  ]

  const toggleDay = (code: string) => {
    const next = byday.includes(code) ? byday.filter((d) => d !== code) : [...byday, code]
    onChange({ freq, byday: next, until })
  }

  return (
    <div className="field">
      <span>Repeats</span>
      <div className="chiprow">
        {options.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="chipbtn"
            aria-current={freq === value ? 'page' : undefined}
            disabled={disabled}
            onClick={() =>
              onChange({
                freq: value,
                // Default a weekly rule to the day the event actually starts, so
                // picking "Weekly" alone already means something sensible.
                byday:
                  value === 'WEEKLY' && byday.length === 0 ? [DAY_CODES[start.getDay()]] : byday,
                until,
              })
            }
          >
            {label}
          </button>
        ))}
      </div>

      {freq === 'WEEKLY' && (
        <div className="chiprow" style={{ marginTop: 6 }}>
          {DAY_CODES.map((code, i) => (
            <button
              key={code}
              type="button"
              className="chipbtn chipbtn--day"
              aria-current={byday.includes(code) ? 'page' : undefined}
              aria-label={code}
              disabled={disabled}
              onClick={() => toggleDay(code)}
            >
              {DAY_LABELS[i]}
            </button>
          ))}
        </div>
      )}

      {freq !== 'NONE' && (
        <label className="field" style={{ marginTop: 6 }}>
          <span>Until (optional)</span>
          <input
            type="date"
            value={until}
            min={format(start, 'yyyy-MM-dd')}
            disabled={disabled}
            onChange={(e) => onChange({ freq, byday, until: e.target.value })}
          />
        </label>
      )}
    </div>
  )
}
