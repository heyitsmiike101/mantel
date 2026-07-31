# Configuration reference

**Nearly everything is configured in the app, under Settings.** Google Calendar, weather, the
screensaver, sharing links and Home Assistant all live there, each with instructions on the
page, and they take effect immediately — no file to edit, no container to restart.

`.env` holds only what must exist before the app can start:

- **`SECRET_KEY`** — encrypts your Google client secret and everyone's OAuth tokens, so it has
  to be available before anything can be read out of the database.
- **`PORT`** and a few operational knobs (database URL, sync intervals, CORS).

Both are covered below. Everything else in this document is a Settings screen.

---

## `.env` — server settings

### `PORT`

Default `8080`. The port on the host machine. Change it if something else already uses 8080.
If you change it, update `PUBLIC_BASE_URL` and your Google redirect URI to match.

### `PUBLIC_BASE_URL` *(legacy — set it in Settings → Google instead)*

The address family members type into a browser, used to build the Google OAuth redirect. It now
lives in **Settings → Google**, which also shows you the exact redirect URI to give Google and
defaults to whatever address you are currently browsing on.

A value here is read once on first start and copied into the app's settings, so an installation
that predates the Settings screen keeps working. After that the Settings value wins.

### `SECRET_KEY`

Default is an insecure placeholder — **set your own**. It encrypts Google tokens at rest and
signs the OAuth state parameter. Generate one with:

```bash
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
```

Any string works (it gets hashed into a key if it isn't already a Fernet key), but a generated
one is best. Changing it invalidates stored Google tokens — accounts show "Needs reconnecting"
and each person reconnects once. No calendar data is lost.

### `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` *(legacy — set them in Settings → Google)*

Configure Google in **Settings → Google**. That page walks you through creating the credentials,
shows the redirect URI to paste into Google Cloud, and lets each person connect their own email.
The client secret is encrypted at rest with `SECRET_KEY` and is never readable back through the
API.

Values here are seeded into the database once on first start, for installations that predate the
Settings screen. Leave them empty on a new install.

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

### Settings → Screen

For a wall display that is on all day. All of it is per-installation, shared by every screen.

| Setting                   | Values                              | Notes                                                           |
| ------------------------- | ----------------------------------- | --------------------------------------------------------------- |
| **Screensaver**           | photos-else-clock, photos, clock, off | What appears when nobody has touched the screen                 |
| **Starts after**          | 1–60 minutes                        | Idle time before the screensaver appears                        |
| **Seconds per photo**     | 5–120 seconds                       | Slideshow pace                                                  |
| **Shuffle**               | on / off                            | Random or upload order                                          |
| **Dark overnight**        | on / off + hours                    | Blanks the page overnight. Crossing midnight (23→7) works        |
| **Burn-in protection**    | on / off                            | Nudges the layout a few pixels every 10 minutes                  |

Photos are uploaded on the same tab. They are re-encoded on upload, which resizes anything
huge and **strips EXIF metadata including GPS coordinates** — worth knowing if you're
uploading photos straight off a phone. They're stored in `photos/` next to the database, so
the backup below already covers them.

**A browser cannot switch a monitor's backlight off.** The overnight setting blanks the *page*,
which is enough for an LCD in a dark room but still draws power and still ages the panel. For
real screen-off, see the screen-power section of
[kiosk-setup.md](kiosk-setup.md) — on a Raspberry Pi that's `wlopm` on a cron schedule.

### Settings → Weather

Free and keyless: the **National Weather Service** inside the United States (which also brings
watches and warnings), and **Open-Meteo** everywhere else. There is no account to create and no
API key to paste. Set a location by searching for a town or postcode.

| Setting      | Values                                    | Notes                                        |
| ------------ | ----------------------------------------- | -------------------------------------------- |
| **Location** | search by name                            | Stored as coordinates                        |
| **Units**    | Fahrenheit, Celsius                       |                                              |
| **Source**   | Automatic, Weather Service, Open-Meteo    | Automatic picks by location                  |

Forecasts are cached for 30 minutes. If the weather service is unreachable the last good
forecast keeps showing with a "cached" marker rather than the panel going blank.

### Settings → Sharing

A read-only iCalendar feed so phones can subscribe and Home Assistant can read the calendar.
See [sharing-and-home-assistant.md](sharing-and-home-assistant.md) for the walkthrough.

| Setting                  | Notes                                                          |
| ------------------------ | -------------------------------------------------------------- |
| **Feed links**           | One for everything, one per calendar. The URL is the credential |
| **Home Assistant URL**   | Optional; enables push-refresh so HA isn't a day stale          |
| **Long-lived token**     | Created in Home Assistant under your profile → Security         |
| **Calendar entity**      | The entity Remote Calendar created                              |

The feed token is derived from `SECRET_KEY`, so it is stable across restarts and **rotating
`SECRET_KEY` revokes every feed link**.

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
| Database            | `mantel-data` Docker volume, `/data/family.db` |
| Screensaver photos  | The same volume, `/data/photos/`                        |
| Google tokens       | Encrypted inside that database                         |
| Version             | The `VERSION` file at the repo root                    |
| Server settings     | `.env`                                                 |
| Display preferences | The database (`app_settings` table)                    |
