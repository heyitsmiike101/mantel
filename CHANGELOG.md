# Changelog

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
