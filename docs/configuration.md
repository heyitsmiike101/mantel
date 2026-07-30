# Configuration reference

Two places hold configuration:

1. **`.env`** — server settings. Read at startup; change them and restart with `./run.sh`.
2. **Settings screen** — display preferences shared by every screen, stored in the database and
   applied immediately. Also available at `GET/PATCH /api/settings`.

---

## `.env` — server settings

### `PORT`

Default `8080`. The port on the host machine. Change it if something else already uses 8080.
If you change it, update `PUBLIC_BASE_URL` and your Google redirect URI to match.

### `PUBLIC_BASE_URL`

Default `http://localhost:8080`. The address family members actually type into a browser.
Used to build the Google OAuth redirect, so it **must exactly match** the redirect URI you
registered in Google Cloud — same scheme, host, and port.

Examples: `http://localhost:8080`, `http://192.168.1.50:8080`, `http://calendar.local:8080`

### `SECRET_KEY`

Default is an insecure placeholder — **set your own**. It encrypts Google tokens at rest and
signs the OAuth state parameter. Generate one with:

```bash
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
```

Any string works (it gets hashed into a key if it isn't already a Fernet key), but a generated
one is best. Changing it invalidates stored Google tokens — accounts show "Needs reconnecting"
and each person reconnects once. No calendar data is lost.

### `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`

Empty by default, which simply means Google sync is turned off and the app runs as a local
calendar. Fill them in from your Google Cloud OAuth client — see
[setup-google-oauth.md](setup-google-oauth.md).

### `SYNC_INTERVAL_SECONDS`

Default `300` (5 minutes). How often the app pulls changes from Google. Lowering it makes
Google-side edits appear faster at the cost of more API calls; a family is nowhere near
Google's quotas, so `60` is fine if you want it snappier.

### `PUSH_INTERVAL_SECONDS`

Default `15`. A safety net for retrying failed pushes. Normal edits don't wait for it — saving
an event wakes the push loop immediately, so changes reach Google in about a second.

### `SYNC_PAST_DAYS`

Default `90`. How far back to import events the first time a calendar syncs. Raise it if you
want more history on the wall; it only affects the initial import.

### `SYNC_ENABLED`

Default `true`. Set to `false` to pause all Google syncing without unlinking anyone — useful
while debugging or if you're travelling with the display.

### `DATABASE_URL`

Default `sqlite:////data/family.db` (inside the container's `/data` volume).

SQLite is the right choice for a family. It runs in WAL mode, so many screens can read while
someone is editing, and simultaneous writes queue for up to 10 seconds rather than failing.
If you ever outgrow it, point this at Postgres — the app uses SQLAlchemy, so nothing else
changes:

```
DATABASE_URL=postgresql+psycopg://user:password@dbhost:5432/familycalendar
```

(You'll need to add the `psycopg` package to the image.)

### `CORS_ORIGINS`

Default `*`. Which origins may call the API from a browser. `*` is reasonable on a home
network. Set a comma-separated list to lock it down.

### `APP_VERSION` / `BUILD_TIME`

Set automatically by `run.sh` from the `VERSION` file. `APP_VERSION` is what the version badge
shows and what screens compare against to decide whether to reload. You shouldn't set these by
hand.

---

## Settings screen

Under **Settings → Display**. Stored in the database, shared by every screen, applied
instantly — no restart.

| Setting             | Values                         | Notes                                                     |
| ------------------- | ------------------------------ | --------------------------------------------------------- |
| **Text size**       | `normal`, `large`, `wall`      | `wall` scales text *and* the hour rows for a mounted screen |
| **Week starts on**  | Sunday, Monday                 | Affects week and month views                              |
| **Clock**           | 12-hour, 24-hour               |                                                           |
| **Day starts/ends** | any hour                       | The visible hour range in the time-grid views             |

Also stored, currently only settable through the API (`PATCH /api/settings`):

| Key                   | Default              | Notes                                          |
| --------------------- | -------------------- | ---------------------------------------------- |
| `home_timezone`       | `America/New_York`   | The household's timezone                       |
| `default_view`        | `week`               | Where `/` redirects                            |
| `kiosk_default_route` | `/calendar/week`     | Suggested landing route for a wall display     |

---

## Where things live

| What                | Where                                                  |
| ------------------- | ------------------------------------------------------ |
| Database            | `family-calendar-data` Docker volume, `/data/family.db` |
| Google tokens       | Encrypted inside that database                         |
| Version             | The `VERSION` file at the repo root                    |
| Server settings     | `.env`                                                 |
| Display preferences | The database (`app_settings` table)                    |
