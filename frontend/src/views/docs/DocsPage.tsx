import { useQuery } from '@tanstack/react-query'

/** Renders the same markdown that /api/ai-guide serves, so the in-app page and the copy an
 *  agent fetches can never drift apart. Deliberately a tiny renderer rather than a markdown
 *  dependency -- the guide only uses headings, tables, lists, code and links. */
export function DocsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['ai-guide'],
    queryFn: async () => (await fetch('/api/ai-guide')).text(),
    refetchInterval: false,
  })

  return (
    <div className="docs">
      <div className="docs__bar">
        <h1 className="docs__title">API documentation</h1>
        <a className="iconbtn" href="/api/docs" target="_blank" rel="noreferrer">
          Interactive docs
        </a>
        <a className="iconbtn" href="/api/openapi.json" target="_blank" rel="noreferrer">
          OpenAPI schema
        </a>
      </div>
      <div className="docs__body">
        {isLoading ? <p>Loading…</p> : <Markdown source={data ?? ''} />}
      </div>
    </div>
  )
}

function Markdown({ source }: { source: string }) {
  const blocks: React.ReactNode[] = []
  const lines = source.split('\n')
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    if (line.startsWith('```')) {
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++])
      i++
      blocks.push(<pre key={key++}>{code.join('\n')}</pre>)
      continue
    }

    if (line.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        const cells = lines[i].split('|').slice(1, -1).map((c) => c.trim())
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells)
        i++
      }
      const [head, ...body] = rows
      blocks.push(
        <div className="docs__tablewrap" key={key++}>
          <table>
            <thead>
              <tr>
                {head.map((c, n) => (
                  <th key={n}>{inline(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, n) => (
                <tr key={n}>
                  {r.map((c, m) => (
                    <td key={m}>{inline(c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const Tag = (['h1', 'h2', 'h3', 'h4'] as const)[level - 1]
      blocks.push(<Tag key={key++}>{inline(heading[2])}</Tag>)
      i++
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ''))
        i++
      }
      blocks.push(
        <ul key={key++}>
          {items.map((t, n) => (
            <li key={n}>{inline(t)}</li>
          ))}
        </ul>,
      )
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push(
        <ol key={key++}>
          {items.map((t, n) => (
            <li key={n}>{inline(t)}</li>
          ))}
        </ol>,
      )
      continue
    }

    if (line.trim() === '' || line.startsWith('---')) {
      i++
      continue
    }

    const para: string[] = []
    while (i < lines.length && lines[i].trim() !== '' && !/^[#|`\-*]|^\d+\./.test(lines[i])) {
      para.push(lines[i++])
    }
    blocks.push(<p key={key++}>{inline(para.join(' '))}</p>)
  }

  return <>{blocks}</>
}

/** Handles `code`, **bold**, and [links](url) -- the only inline syntax the guide uses. */
function inline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    if (match[1]) out.push(<code key={key++}>{match[1]}</code>)
    else if (match[2]) out.push(<strong key={key++}>{match[2]}</strong>)
    else
      out.push(
        <a key={key++} href={match[4]} target="_blank" rel="noreferrer">
          {match[3]}
        </a>,
      )
    last = pattern.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
