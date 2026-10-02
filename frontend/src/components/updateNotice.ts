/** Pure helpers for the nav version badge and its About popover. */

export interface UpdateInfo {
  version: string
  latest_version?: string | null
  update_available?: boolean
  release_url?: string | null
}

/** The badge's single-line text, also used as its accessible name. */
export function versionBadgeLabel(version: string, updateAvailable: boolean): string {
  return updateAvailable ? `v${version} · Update available` : `v${version}`
}

/** Only trust an update flag that comes with a version to name; a half-filled
 *  response must never light the badge with nothing to say in the popover. */
export function hasUpdate(info: UpdateInfo): boolean {
  return Boolean(info.update_available && info.latest_version)
}

/** Where "View release" may point. The URL arrives from the server, so anything that
 *  is not an https GitHub link is dropped rather than rendered as a clickable href. */
export function safeReleaseUrl(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && u.hostname === 'github.com' ? u.href : null
  } catch {
    return null
  }
}

/** The one-line Docker upgrade hint. Pins the new tag, because `latest` would also
 *  work but would hide which version the container is really on. */
export function dockerUpgradeHint(latest: string): string {
  return `docker pull ghcr.io/heyitsmiike101/mantel:${latest}, then recreate the container (docker compose up -d).`
}
