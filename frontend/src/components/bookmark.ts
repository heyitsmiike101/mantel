/** The top-bar shortcut is a URL anyone on the network can set, and it ends up in an
 *  `href`. `javascript:` and `data:` URLs in an href execute on click, so on a no-auth
 *  LAN app that is a stored-XSS hole wearing a settings field. Only http and https are
 *  allowed through; anything else is treated as no bookmark at all.
 *
 *  A bare host like `dash.lan/?view=wall` is a URL a person would reasonably type, so it
 *  gets http:// rather than a rejection. */
export function safeBookmarkUrl(raw: string | null | undefined): string | null {
  const value = (raw ?? '').trim()
  if (!value) return null

  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(value) ? value : `http://${value}`

  let url: URL
  try {
    url = new URL(candidate)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  return url.href
}

/** What to print on the button. Falls back to the hostname so a bookmark with a URL and
 *  no label is still recognisable, rather than rendering an empty button. */
export function bookmarkLabel(label: string | null | undefined, url: string): string {
  const trimmed = (label ?? '').trim()
  if (trimmed) return trimmed
  try {
    return new URL(url).hostname
  } catch {
    return 'Bookmark'
  }
}
