import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Markdown } from './Markdown'

const render = (source: string) => renderToStaticMarkup(<Markdown source={source} />)

const GUIDE = fileURLToPath(new URL('../../../docs/ai-guide.md', import.meta.url))

describe('Markdown', () => {
  // The bug this file exists for: a line starting with an inline code span was
  // rejected by every block branch *and* by the paragraph loop, so `i` never
  // advanced. The whole API page hung the browser tab rather than failing loudly.
  it('renders a paragraph line that begins with a code span', () => {
    const html = render('Only calendars with\n`"writable": true` accept new events.\n')
    expect(html).toContain('<code>&quot;writable&quot;: true</code>')
    expect(html).toContain('accept new events.')
  })

  it('never leaves a line unconsumed, whatever it starts with', () => {
    // Every one of these was, or could become, a line no branch claims.
    for (const line of ['`code` first', '*not a bullet*', '-nospace', '#nospace', '#'.repeat(7) + ' deep', '> ', '|']) {
      expect(() => render(line + '\n')).not.toThrow()
    }
  })

  it('renders the real ai-guide the app ships', () => {
    const html = render(readFileSync(GUIDE, 'utf8'))
    // The doc's own subject, not the product name -- this assertion used to say
    // "Family Calendar" and broke the build the day the app was renamed, which
    // told us nothing about whether the markdown still rendered.
    expect(html).toContain('API guide for AI agents')
    expect(html).toContain('<table>')
    expect(html).toContain('<pre>')
    // The line that used to hang, rendered.
    expect(html).toContain('accept new events.')
  })

  it('renders headings, lists, tables, quotes and code fences', () => {
    const html = render(
      [
        '# Title',
        '',
        '- one',
        '- two',
        '',
        '1. first',
        '',
        '> quoted **bold**',
        '',
        '| a | b |',
        '| - | - |',
        '| 1 | 2 |',
        '',
        '```',
        'code line',
        '```',
      ].join('\n'),
    )
    expect(html).toContain('<h1>Title</h1>')
    expect(html).toContain('<li>one</li>')
    expect(html).toContain('<ol>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<th>a</th>')
    expect(html).toContain('<td>1</td>')
    expect(html).toContain('<pre>code line</pre>')
  })

  it('drops a table that is nothing but a separator row', () => {
    // Destructuring head out of an empty rows array used to throw here.
    expect(render('| --- | --- |\n')).toBe('')
  })

  it('survives an unterminated code fence', () => {
    expect(render('```\nno closing fence\n')).toContain('no closing fence')
  })

  it('renders links, bold and italic inline', () => {
    const html = render('See [the docs](https://example.com) — **bold** and *italic*.\n')
    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('<strong>bold</strong>')
    expect(html).toContain('<em>italic</em>')
  })
})
