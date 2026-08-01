import { describe, expect, it } from 'vitest'
import { bookmarkLabel, safeBookmarkUrl } from './bookmark'

describe('safeBookmarkUrl', () => {
  it('passes through ordinary http and https links', () => {
    expect(safeBookmarkUrl('http://dash.lan/?view=wall')).toBe('http://dash.lan/?view=wall')
    expect(safeBookmarkUrl('https://example.com/a/b')).toBe('https://example.com/a/b')
    expect(safeBookmarkUrl('http://basilisk-bytes:8787/?view=wall')).toBe(
      'http://basilisk-bytes:8787/?view=wall',
    )
  })

  it('assumes http:// for a bare host, which is what people type', () => {
    expect(safeBookmarkUrl('dash.lan/?view=wall')).toBe('http://dash.lan/?view=wall')
  })

  it('refuses schemes that execute — this field is writable by anyone on the LAN', () => {
    expect(safeBookmarkUrl('javascript:alert(1)')).toBeNull()
    expect(safeBookmarkUrl('JavaScript:alert(1)')).toBeNull()
    expect(safeBookmarkUrl('data:text/html,<script>alert(1)</script>')).toBeNull()
    expect(safeBookmarkUrl('vbscript:msgbox(1)')).toBeNull()
    expect(safeBookmarkUrl('file:///etc/passwd')).toBeNull()
  })

  it('treats blank as no bookmark', () => {
    expect(safeBookmarkUrl('')).toBeNull()
    expect(safeBookmarkUrl('   ')).toBeNull()
    expect(safeBookmarkUrl(null)).toBeNull()
    expect(safeBookmarkUrl(undefined)).toBeNull()
  })
})

describe('bookmarkLabel', () => {
  it('uses the label when there is one', () => {
    expect(bookmarkLabel('wall', 'http://dash.lan/')).toBe('wall')
    expect(bookmarkLabel('  Wall  ', 'http://dash.lan/')).toBe('Wall')
  })

  it('falls back to the hostname rather than an empty button', () => {
    expect(bookmarkLabel('', 'http://dash.lan/?view=wall')).toBe('dash.lan')
    expect(bookmarkLabel(null, 'http://basilisk-bytes:8787/')).toBe('basilisk-bytes')
  })
})
