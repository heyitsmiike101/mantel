/** A tiny markdown renderer for the AI guide that /api/ai-guide serves, so the in-app page
 *  and the copy an agent fetches can never drift apart. Deliberately not a markdown
 *  dependency -- the guide only uses headings, tables, lists, quotes, code and links.
 *
 *  The one rule this file must never break: every branch of the block loop advances `i`.
 *  An earlier version let a paragraph start be rejected without consuming the line, and a
 *  guide line beginning with a backtick span spun forever and hung the tab. There is a test
 *  for exactly that.
 */

export function Markdown({ source }: { source: string }) {
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
      i++ // closing fence, or past the end for an unterminated one
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
      // A table of nothing but a separator row leaves `rows` empty; skip it rather
      // than destructuring `undefined` into head.
      if (rows.length > 0) {
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
      }
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      const level = Math.min(heading[1].length, 6)
      const Tag = (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] as const)[level - 1]
      blocks.push(<Tag key={key++}>{inline(heading[2])}</Tag>)
      i++
      continue
    }

    if (isBullet(line)) {
      const items: string[] = []
      while (i < lines.length && isBullet(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''))
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

    if (isNumbered(line)) {
      const items: string[] = []
      while (i < lines.length && isNumbered(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''))
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

    if (line.startsWith('>')) {
      const quoted: string[] = []
      while (i < lines.length && lines[i].startsWith('>')) {
        quoted.push(lines[i].replace(/^>\s?/, ''))
        i++
      }
      blocks.push(
        <blockquote key={key++}>
          <Markdown source={quoted.join('\n')} />
        </blockquote>,
      )
      continue
    }

    if (line.trim() === '' || /^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      i++
      continue
    }

    // Paragraph. The first line is always consumed -- that is what stops this loop
    // from spinning on a line the other branches declined.
    const para: string[] = [lines[i++]]
    while (i < lines.length && !startsBlock(lines[i])) para.push(lines[i++])
    blocks.push(<p key={key++}>{inline(para.join(' '))}</p>)
  }

  return <>{blocks}</>
}

function isBullet(line: string): boolean {
  return /^\s*[-*]\s+/.test(line)
}

function isNumbered(line: string): boolean {
  return /^\s*\d+\.\s+/.test(line)
}

/** Would this line start a new block? Used to decide where a paragraph ends. A leading
 *  backtick is not on this list: `code` at the start of a line continues the paragraph. */
function startsBlock(line: string): boolean {
  return (
    line.trim() === '' ||
    line.startsWith('```') ||
    line.startsWith('|') ||
    line.startsWith('>') ||
    /^#{1,6}\s/.test(line) ||
    /^(-{3,}|\*{3,}|_{3,})\s*$/.test(line) ||
    isBullet(line) ||
    isNumbered(line)
  )
}

/** Handles `code`, **bold**, *italic* and [links](url) -- the only inline syntax the guide uses. */
export function inline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*|\[([^\]]+)\]\(([^)]+)\)/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    if (match[1] !== undefined) out.push(<code key={key++}>{match[1]}</code>)
    else if (match[2] !== undefined) out.push(<strong key={key++}>{match[2]}</strong>)
    else if (match[3] !== undefined) out.push(<em key={key++}>{match[3]}</em>)
    else
      out.push(
        <a key={key++} href={match[5]} target="_blank" rel="noreferrer">
          {match[4]}
        </a>,
      )
    last = pattern.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
