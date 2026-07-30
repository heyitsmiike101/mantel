# Family Calendar

A self-hosted family calendar for a wall-mounted touchscreen — and every other screen in the
house. Runs in one Docker container on your own network, syncs both ways with Google Calendar,
and has no login because it lives behind your front door.

- **Real two-way Google sync.** Add an event on the wall display and it appears in Google
  within seconds — and the other way round. This is rarer than it sounds: Nextcloud can't do it
  at all (Google requires OAuth, which Nextcloud can't do for calendar subscriptions), and Home
  Assistant's CalDAV integration can only create events, never edit or delete them.
- **Four views** — today, 3-day, week, month — all touch-first, portrait and landscape
- **A person per color.** Everyone can link as many Google accounts as they like and claim the
  calendars they own
- **A customizable dashboard wall** you build from widgets
- **Updates itself.** Wall tablets hard-reload on their own when you deploy a new version, so
  nobody has to go find the refresh button
- **Runs on a Raspberry Pi.** Multi-architecture images for `amd64` and `arm64`
- **Everything is an API**, documented for both humans and AI agents
- **No subscription, no account, no cloud.** It's your data on your hardware

## Quick start

```bash
git clone <your-fork-url> family-calendar
cd family-calendar
cp .env.example .env
./run.sh
```

Open <http://localhost:8080>. That's it — you have a working family calendar with a local
"Family" calendar and no Google setup required.

To reach it from other devices, use the machine's LAN address, e.g. `http://192.168.1.50:8080`.

## Adding Google Calendar

Optional, and worth it if your family already lives in Google Calendar. It takes about ten
minutes and you only do it once for the whole household:

**→ [docs/setup-google-oauth.md](docs/setup-google-oauth.md)**

After that, each family member clicks **Connect a Google account** in Settings and signs in
with their own account. Events created on the wall display appear in Google within seconds, and
changes made in Google appear on the wall on the next sync.

## Setting up a wall display

1. Add the family members under **Settings → Family** and give each one a color.
2. Under **Settings → Display**, set text size to **wall** so it's readable from across the room.
3. Point the tablet's browser at the app and put it in kiosk / full-screen mode.
4. Pick the route you want it to sit on — `/dashboard` or `/calendar/week` are the usual choices.

The screen keeps itself current: data refreshes every minute, and when you deploy a new version
the page hard-reloads on its own within a minute. The version number is always visible in the
corner of the navigation bar.

**→ [docs/kiosk-setup.md](docs/kiosk-setup.md)** covers this properly: Chromium kiosk mode on a
Raspberry Pi, Fully Kiosk on Android, Guided Access on an iPad, how to actually turn the screen
off at night (the command most tutorials give you stopped working in Raspberry Pi OS Bookworm),
and how to stop a permanently-charging wall tablet's battery from swelling.

## Running on a Raspberry Pi

The image is built for `linux/amd64` and `linux/arm64`, so a Pi 4 or Pi 5 runs the same tag as
a desktop. `./run.sh` works unchanged on the Pi.

You can also keep the Pi dumb: run the container on a NAS or server, and let the Pi be nothing
but a browser pointed at it. That's lighter, and an SD card failure then costs you nothing.

To build the multi-architecture image yourself:

```bash
./build.sh --push ghcr.io/yourname/family-calendar
```

On an x86 machine that needs QEMU registered once for the arm64 half:

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

## Upgrading

```bash
git pull
./run.sh
```

Every open screen in the house picks up the new version within a minute. No refreshing, no
walking around with a keyboard.

## Configuration

Everything is set in `.env`. Every option is documented in
**[docs/configuration.md](docs/configuration.md)**, and `.env.example` explains each one inline.
The short version:

| Variable                | Default                     | What it does                                        |
| ----------------------- | --------------------------- | --------------------------------------------------- |
| `PORT`                  | `8080`                      | Port the app is served on                           |
| `PUBLIC_BASE_URL`       | `http://localhost:8080`     | How family members reach the app; must match Google |
| `SECRET_KEY`            | *(insecure default)*        | Encrypts stored Google tokens — set your own        |
| `GOOGLE_CLIENT_ID`      | empty                       | From your Google Cloud OAuth client                 |
| `GOOGLE_CLIENT_SECRET`  | empty                       | From your Google Cloud OAuth client                 |
| `SYNC_INTERVAL_SECONDS` | `300`                       | How often to pull changes from Google               |
| `SYNC_PAST_DAYS`        | `90`                        | How far back to import on the first sync            |
| `DATABASE_URL`          | `sqlite:////data/family.db` | Where data lives                                    |

## The API

Every feature in the UI is backed by an endpoint, so you can wire the calendar into anything
else you run at home.

- **Interactive docs:** `/api/docs`
- **Schema:** `/api/openapi.json`
- **Guide written for AI agents:** `/api/ai-guide` — also readable at
  [docs/ai-guide.md](docs/ai-guide.md)
- **Wall display setup:** [docs/kiosk-setup.md](docs/kiosk-setup.md)

```bash
# What's on this week?
curl "http://localhost:8080/api/events?start=2026-08-02T00:00:00Z&end=2026-08-09T00:00:00Z"

# Add something
curl -X POST http://localhost:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"calendar_id":1,"title":"Dentist","start_at":"2026-08-05T14:00:00Z","end_at":"2026-08-05T15:00:00Z"}'
```

There is **no authentication** — the app assumes it is on a trusted home network. Don't expose
it directly to the internet. If you need access from outside the house, put it behind a VPN
such as Tailscale or WireGuard.

## Data and backups

Everything lives in a single SQLite database inside the `family-calendar-data` Docker volume.
To back it up:

```bash
docker run --rm -v family-calendar-data:/data -v "$PWD":/backup alpine \
  cp /data/family.db /backup/family-backup.db
```

SQLite runs in WAL mode, so every screen in the house can read while someone is editing, and
concurrent edits queue rather than fail. That is plenty for a family. If you ever want
something heavier, point `DATABASE_URL` at Postgres — no code changes needed.

> **Note:** don't put the database on a cloud-synced folder (OneDrive, Dropbox, iCloud). Their
> file-locking behavior can corrupt SQLite. The default Docker volume is safe.

## Development

```bash
# Backend
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv -e ".[dev]"
DATABASE_URL="sqlite:///../data/family.db" .venv/bin/uvicorn app.main:app --reload --port 8080
.venv/bin/python -m pytest

# Frontend (proxies /api to :8080)
cd frontend
npm install
npm run dev
npm test
```

## License

MIT — see [LICENSE](LICENSE).
