/** Will Google accept a redirect URI built from this address?
 *
 * Google's console rejects most of what a homelab actually looks like, and it
 * does so at the point you paste the URI -- long after the setup page has told
 * you to copy it. The rules (developers.google.com/identity/protocols/oauth2/web-server):
 *
 *   - HTTPS required, except for localhost
 *   - raw IP addresses rejected, except loopback
 *   - the host's TLD must be on the public suffix list, which rules out
 *     `debian-docker`, `calendar.local` and `something.localhost` alike
 *
 * So the honest answer for a LAN install is "this address will not work; use
 * localhost for the one-time connect, or put it behind a real HTTPS domain".
 * Returning that as a sentence beats letting Google say "Invalid Redirect".
 */
export function googleRedirectProblem(baseUrl: string): string | null {
  let url: URL
  try {
    url = new URL(baseUrl)
  } catch {
    return "That doesn't look like a URL. It should start with http:// or https://."
  }

  // `new URL('debian-docker:8099')` succeeds -- it reads the host as a *scheme* and
  // leaves the hostname empty. Without this check that sails into the rules below
  // and produces a message about an empty hostname.
  if ((url.protocol !== 'http:' && url.protocol !== 'https:') || !url.hostname) {
    return "That doesn't look like a URL. It should start with http:// or https://."
  }

  const host = url.hostname
  // Exactly loopback. Google rejects `.localhost` subdomains despite the name.
  if (host === 'localhost' || host === '127.0.0.1' || host === '[::1]' || host === '::1') {
    return null
  }

  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    return (
      `Google rejects IP addresses like ${host} as redirect URIs — only loopback is ` +
      `allowed. Use localhost for the one-time connect, or a real domain over HTTPS.`
    )
  }

  if (!host.includes('.') || host.endsWith('.local') || host.endsWith('.localhost')) {
    return (
      `Google needs a hostname ending in a public domain such as .com — “${host}” isn't ` +
      `one, so it will answer “Invalid Redirect”. Use localhost for the one-time connect, ` +
      `or a real domain over HTTPS.`
    )
  }

  if (url.protocol !== 'https:') {
    return (
      `Google only accepts plain http:// for localhost. ${host} needs https://, which ` +
      `means a reverse proxy with a certificate — or use localhost for the one-time connect.`
    )
  }

  return null
}

/** An SSH tunnel that makes the app reachable on loopback, so the one-time connect
 *  can use a redirect URI Google accepts. Null when the address is too broken to
 *  build one from -- the banner that shows this must not throw on bad input. */
export function tunnelCommand(baseUrl: string): string | null {
  try {
    const url = new URL(baseUrl)
    if (!url.hostname) return null
    const port = url.port || (url.protocol === 'https:' ? '443' : '80')
    return `ssh -L ${port}:localhost:${port} ${url.hostname}`
  } catch {
    return null
  }
}

/** The address to suggest instead: same port, on loopback. */
export function localhostAlternative(baseUrl: string): string {
  try {
    const url = new URL(baseUrl)
    return `http://localhost${url.port ? `:${url.port}` : ''}`
  } catch {
    return 'http://localhost:8080'
  }
}
