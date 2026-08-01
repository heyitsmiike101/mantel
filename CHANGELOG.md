# Changelog

## 0.3.0

**A configurable shortcut button on every page.** Set a label and a link under
Settings → Display and a button appears in a slim bar at the top of every screen —
for jumping to another dashboard, a camera page, whatever the wall display should be
one tap away from.

It is off by default. With no link set the bar isn't rendered and its grid row
collapses to nothing, so an install that doesn't use it pays no vertical space —
which is the resource a wall display has least of.

The link is restricted to `http` and `https`. This is a field anyone on the network
can write, and it lands in an `href`, so a `javascript:` URL would otherwise be
stored XSS wearing a settings field. A bare host like `dash.lan/?view=wall` is
accepted and gets `http://` added, since that's what people type.

## 0.2.12

**`/api/sync/status` said Google wasn't configured even when it was.** Credentials moved
out of `.env` and into the database in 0.2.2; this endpoint kept reading the environment,
so it reported `google_configured: false` on every install that set Google up through the
Settings page — which is all of them. The Settings page itself was always correct.

## 0.2.11

**Connecting a Google account no longer ends in a 500 when Google withholds calendar
access.** Asking for a scope is not the same as getting one: if the Calendar API isn't
enabled on the project, Google signs the person in, silently drops the calendar scope,
and returns a perfectly valid token. The app stored that account, then crashed on the
first calendar call with an unhandled 403.

Now the token's granted scopes are checked before anything is saved, and the person is
told what to fix — the Calendar API, or the scope under Data Access — in the app rather
than in a stack trace. A calendar listing that fails for any other reason marks the
account as needing attention instead of returning a server error.

**The Settings page shows OAuth errors at all now.** The callback could only report
failures through `?error=` on the redirect, and nothing read it, so every failed
connection looked identical to a cancelled one.

## 0.2.10

**Documented the setup that actually works on a home network.** The Google guide now has an
end-to-end walkthrough for pointing a subdomain you own at your reverse proxy: the DNS record,
why HTTP-01 certificates can never work for a private address and DNS-01 must be used instead,
config for Nginx Proxy Manager / Caddy / Traefik, and the DNS-rebinding-protection gotcha that
makes a name resolve on some devices and not others.

It ends with four `curl` checks that isolate a failure in order, including the one that matters
most: opening the callback path by hand should return the app's own 422 about a missing `state`
parameter. That "error" is the proof the route reaches the app — an HTML 404 or a 502 means the
proxy never forwarded it.

## 0.2.9

**The redirect-URI check now catches private domains like `.lan`.** 0.2.8 warned about
IP addresses, bare hostnames and `.local`, but waved through anything else that had a
dot in it and used HTTPS — so a reverse proxy serving `https://family.lan`, which is
what a lot of homelabs look like, was told it was fine and then refused by Google.
`.lan`, `.home`, `.internal`, `.corp`, `.intranet`, `.private` and friends are now
rejected with an explanation, because a valid certificate makes no difference: the
name has to be under a domain you actually own.

The setup guide adds the useful half of that: the name doesn't have to be reachable
from the internet. Google never fetches the redirect URI — your browser does — so a
record under your own domain pointing at a LAN address works, and you can keep
`family.lan` on the same proxy for everyday use.

## 0.2.8

**Fixed the Google setup advice for anyone on a home network.** Google refuses most
LAN addresses as OAuth redirect URIs — no IP addresses, no `.local`, no bare machine
names, and plain `http://` only for `localhost` — so following the old instructions
ended at *"Invalid Redirect: must end with a public top-level domain"*. The examples
in the docs were addresses Google would never have accepted.

Settings → Google now checks your address before you go anywhere near the console,
and if Google would refuse it, says so and gives you the two ways out: register the
loopback URI and do the one-time connect over an SSH tunnel (it prints the exact
command for your host), or put the app behind a real HTTPS name such as
`tailscale serve`. The redirect URI is only used while connecting — refreshing a
token never touches it — so the tunnel is needed once per person and never again.

## 0.2.7

- **A typo in an event filter no longer reads as a broken server.**
  `GET /api/events?calendar_ids=abc` answered 500; it now answers 400 naming the
  field. `user_ids` had the same fault. This matters most for the integration path
  the AI guide documents: 500 is the one status a client treats as "retry later"
  rather than "fix your request", so a typo could turn into a retry loop against a
  perfectly healthy calendar. Trailing and repeated commas still work — `,1,,` is
  sloppy, not wrong. Found by a tool building a wall-display widget against the API.
- Released images now report `build_time` as ISO-8601 instead of a bare epoch.

## 0.2.6

- **Prebuilt images actually get a `latest` tag.** The release workflow only runs on a
  `v*` tag, where `is_default_branch` is false — so the guard on the `latest` tag meant
  it was never published. `docker run ghcr.io/heyitsmiike101/mantel:latest` works from
  this release on.
- Generating a `SECRET_KEY` is now `openssl rand -base64 32` instead of pulling a Python
  image to call Fernet. Any string works; it gets hashed into a key.

## 0.2.5

Two display fixes, both spotted while capturing the README screenshots.

- **Short events no longer print their title over their time.** A 15-minute block is
  shorter than two lines of text, and the two lines were shrinking below their own
  line boxes and painting on top of each other. Blocks that short now put the time in
  front of the title on one line, and any block that still runs out of room clips
  cleanly instead of overlapping.
- **List names are no longer truncated for no reason.** "Groceries" was rendering as
  "Groce…" with half the card empty, because the Clear and Delete buttons were
  squeezing the title rather than wrapping below it.

## 0.2.4

**Publishing the Google app is now its own step, and you can't miss it.** It was a footnote
inside another step, in a walkthrough that started collapsed — so the one setting that decides
whether your family reconnects every 7 days was the easiest thing on the page to skip. It is now
step 4 of 8, with a warning box explaining that publishing does not submit anything for review.
The walkthrough also opens by default when Google isn't set up yet, and the "needs connecting
again" banner now names Testing mode as the likely cause and links straight to the fix.

**Updated for Google's current console.** The old *APIs & Services → OAuth consent screen* and
*Credentials* pages are now the *Google Auth Platform*, split into Overview, Audience and
Clients. Every link in the app and in docs/setup-google-oauth.md points at the current pages.

## 0.2.3

**The API guide is a tab in Settings.** It used to be its own item in the navigation bar, which
put developer documentation on the same footing as the calendar itself on a wall display. It now
lives under **Settings → API**, alongside links to the interactive docs, the OpenAPI schema and
the raw markdown. An old `/docs` bookmark redirects there.

**Fixed: the API guide hung the browser instead of rendering.** The little markdown renderer had
a loop that could decline a line without consuming it, and one line of the guide — a paragraph
beginning with a `code span` — hit exactly that case, so the tab locked up on a blank page. Every
branch now advances, and the renderer is tested against the real guide the app ships rather than
against a sample.

## 0.2.2

**The family is on the calendar page.** Everyone appears as a chip along the top, filled with
their own colour, so the row doubles as the legend for the grid below. Tap somebody to grey them
out and their events disappear; tap again to bring them back. The choice is remembered per
device, so the kitchen display and your phone can show different things, and somebody added to
the family later shows up straight away rather than arriving hidden. Events on a calendar nobody
has claimed always stay visible — they belong to the household.

**Google is configured in the app now, not in a file.** Settings → Google walks you through
creating the credentials in Google Cloud, with clickable links, the exact redirect URI for your
installation ready to copy, and boxes to paste the Client ID and secret into. It takes effect
immediately — no editing `.env`, no restarting the container. Each family member then presses
**Connect an email** on their own row, and can add as many accounts as they like.

The client secret is encrypted at rest and is never readable back through the API; the same is
now true of the Home Assistant token.

**`.env` is down to two things**: the port, and a `SECRET_KEY` to encrypt everything with. An
existing installation's Google credentials are copied out of `.env` into the app on first start,
so upgrades keep working and Settings shows the truth from then on.

## 0.2.1

Fixes from a code review of the 0.2.0 release.

- **Subscribed calendars no longer show repeating events twice.** Once a series
  has been pushed to Google, Google's expanded instances are the record; the feed
  was also exporting our copy's repeat rule, so subscribers rendered the whole
  series a second time.
- **Events added in Google Calendar now reach Home Assistant.** Only edits made
  in this app were telling HA to refresh, so with HA's own polling switched off
  (as the setup guide instructs) an event added on a phone never appeared there.
- **The dashboard survives a network drop.** Its widget layout, lists and weather
  weren't cached for offline use, so a wall display fell back to the empty-
  dashboard placeholder — only the calendar views actually worked offline.
- **Subscription links now use the address you're browsing on** instead of
  `PUBLIC_BASE_URL`, which defaults to localhost and produced a link that
  silently failed on phones.
- A weather outage can no longer tie up the server: one refresh runs at a time
  and everyone else is served the cached forecast immediately.
- Repeating events that finished long ago are no longer re-expanded on every
  calendar request.
- A future upgrade that needs a manual migration now refuses to start instead of
  booting onto an incomplete database.
- Internal: fixed an ORM hazard in recurrence expansion, and Home Assistant
  refreshes now coalesce onto one worker instead of a thread per write.

## 0.2.0

Wall-display release: everything needed to actually mount this on a wall and live with it.

**Runs on a Raspberry Pi.** Images are built for `linux/amd64` and `linux/arm64`, and
[docs/kiosk-setup.md](docs/kiosk-setup.md) covers Chromium kiosk mode, Fully Kiosk on Android,
iPad Guided Access, turning the screen off at night (the command most guides give you stopped
working in Raspberry Pi OS Bookworm), and keeping a wall tablet's battery from swelling.

**It keeps working when the network doesn't.** A service worker keeps the last known schedule
on screen instead of going blank — deliberately never caching the version endpoint, so the
self-update still works.

**Screensaver.** Photo slideshow or a large clock with today's agenda, an overnight blackout
window, and burn-in protection. Photos are uploaded in Settings, re-encoded on the way in
(which strips EXIF location data), and stored beside the database so backups already cover them.

**Repeating events.** Daily, weekly on chosen days, monthly or yearly, with an optional end
date. Series push to Google as an RRULE.

**Per-person filter.** Tap a family member to see only their week. Remembered per device, so
the kitchen display and a phone can differ.

**Weather**, with no API key and no account: the National Weather Service in the United States
(including watches and warnings) and Open-Meteo everywhere else. Set a location by searching
for a town.

**Shared lists** for groceries and chores, tickable from the wall, with a dashboard widget.

**Countdown widget** for the things everyone's waiting for.

**Subscribe on your phone.** A read-only calendar feed for Apple Calendar, Outlook or Google —
which doubles as the Home Assistant integration: pair it with the push-refresh setting and a
calendar entity in HA updates within a second instead of once a day. No custom component to
install. See [docs/sharing-and-home-assistant.md](docs/sharing-and-home-assistant.md).

**Upgrades apply themselves.** Database columns added by a new release are created at startup,
so `git pull && ./run.sh` no longer needs a manual migration.

## 0.1.0

First release.

- Today, 3-day, week and month calendar views, built for touch in portrait and landscape
- Family members with per-person colors; each can link multiple Google accounts and claim
  the calendars they own
- Two-way Google Calendar sync with incremental pulls, an automatic push queue, and
  last-write-wins conflict handling
- Customizable dashboard wall
- Screens hard-reload themselves when a new version is deployed; the version is always visible
- Full REST API with OpenAPI docs and a guide written for AI agents at `/api/ai-guide`
- Single Docker container, SQLite in WAL mode, no login
