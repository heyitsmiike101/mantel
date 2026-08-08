# Working on Mantel

Notes for an AI agent (or a new human) changing this codebase. For *calling* the API instead,
read [docs/ai-guide.md](docs/ai-guide.md), which is also served at `/api/ai-guide`.

Everything here is something you cannot infer from reading a single file, and most of it will
cost you a debugging session if you don't know it.

## What this is

A self-hosted family calendar for a wall-mounted touchscreen. FastAPI + SQLAlchemy 2.0 behind a
React 19 SPA, shipped as one Docker image. SQLite in WAL mode. No authentication, deliberately —
it runs on a home LAN.

The thing that makes it unusual is **two-way sync**, with both Google Calendar and iCloud. Most
self-hosted calendars only display. Breaking the round trip is the worst regression available.

## The five things that will bite you

### 1. There are no migrations, and you cannot add a NOT NULL column

`backend/app/schema_sync.py` runs at startup and is **additive only**. It can `ADD COLUMN` and
create indexes. It cannot rename a column, change a type, or add a `UniqueConstraint` to a table
that already exists. A NOT NULL column with no literal scalar default **refuses to boot**.

So: **every new column must be nullable**, and if you need uniqueness you must design around the
constraints that already exist. Alembic is not installed; don't reach for it without saying so.

### 2. `google_calendar_id` does not mean Google

`Calendar.google_calendar_id`, `Event.google_event_id` and `Event.google_etag` hold **whatever
the provider uses** — a Google id, or a CalDAV collection path / resource filename / ETag.

The names are wrong and are kept anyway, because the uniqueness that prevents duplicate rows
lives in `uq_account_gcal` and `uq_calendar_gevent`, and per (1) those cannot be recreated on an
existing table. Renaming would ship a database with no duplicate protection.

Read them through the `remote_id` / `remote_etag` properties on the models in new code.

### 3. Every datetime in the database is naive UTC

See `models.utcnow`. SQLite has no timezone storage. Values are re-tagged as UTC on the way out
by `timeutil.as_utc`. All-day events are the exception: naive *dates* with an **exclusive** end,
which is how both Google and iCalendar express them, so that path does no conversion at all.

An iCalendar time with no zone is *floating* — "whatever the clock says here" — and is read in
the `home_timezone` setting, not UTC. Getting that wrong moves the school run by hours.

### 4. Providers disagree about who expands a recurring series

| | Google | iCloud (CalDAV) |
| --- | --- | --- |
| Sends | expanded instances (`singleEvents=true`) | the master, with its RRULE |
| Expanded by | Google | this app, in `services/recurrence.py` |
| `Event.is_master` after push | `True` (hide our copy) | `False` (ours is the one drawn) |

That is what `CalendarProvider.expands_recurrence` decides. A CalDAV resource also carries
*override* components — occurrences somebody moved — in the **same** `.ics` file as the master.
Each becomes its own row (`<filename>#<recurrence-id>`) **and** gets a synthesized EXDATE on the
master, because iCloud sends no EXDATE for these: the `RECURRENCE-ID` *is* the exclusion.
Without that, every moved week renders twice. There is a test that fails if you remove it.

### 5. Last write wins, and the guard is load-bearing

`sync_engine._apply_remote_event` refuses to overwrite a row whose `sync_state != "synced"` —
that is a local edit the push loop hasn't sent yet. `_prune_stale_occurrences` has the same
guard. Removing either lets a background pull silently destroy something a person just typed.

## Layout

```
backend/app/
  models.py            all tables; read the column comments, they carry the reasoning
  schema_sync.py       the "migration" system — see (1)
  routers/             HTTP; docstrings here become the public OpenAPI text
  services/
    sync_engine.py     provider-agnostic: discover, pull, push, conflicts, resync
    providers/
      base.py          RemoteEvent / RemoteCalendar / CalendarProvider — the contract
      google.py        Google JSON <-> RemoteEvent
      icloud.py        VEVENT <-> RemoteEvent
      registry.py      which provider serves which account
    caldav_client.py   CalDAV transport and XML only; knows nothing about models
    google_api.py      Google REST transport only
    icloud_auth.py     app-specific passwords
    google_oauth.py    OAuth tokens
    recurrence.py      RRULE expansion, EXDATE handling
frontend/src/views/settings/   GoogleTab, ICloudTab, SettingsPage
```

**Adding a third provider** should mean a new `providers/*.py` and a branch in `registry.py`.
If you find yourself editing `sync_engine.py` to special-case a service, the abstraction is
leaking — push it back behind the interface.

## Running things

**Docker is the deployment.** `./run.sh` builds and starts it; nothing else is supported.

```bash
./run.sh                       # http://localhost:8080
```

For tests you need a local environment. **Do not assume the checked-out `backend/.venv` or
`frontend/node_modules` work** — this repo is often cloned onto a different OS than the one that
created them, and platform-specific binaries (rollup, esbuild, the Python interpreter itself)
will not run. Build your own if they fail; don't delete theirs.

```bash
cd backend && python -m pytest -q && ruff check app tests
cd frontend && npm run lint && npm test
```

CI runs exactly those, on pushes to `main`, `v*` tags, and PRs to `main` — **not** on feature
branch pushes. Open the PR to get a CI run.

## Conventions worth matching

- **Comments explain why, not what.** The existing ones record the bug that motivated the code
  ("Google drops a scope it cannot grant and still returns a valid token"). Match that; don't
  narrate the syntax.
- **Test names are sentences about behaviour**, and many carry the failure they prevent in the
  assertion message. `test_expired_token_resyncs_without_losing_unpushed_local_events`.
- **Fakes sit at the transport layer**, not at the provider interface — `tests/fake_google.py`
  imitates Google's JSON, `tests/fake_caldav.py` serves real multistatus XML over
  `httpx.MockTransport`. Faking higher up would skip the translation code, which is where the
  bugs actually are.
- **API docstrings are user-facing.** They become the OpenAPI description and are read by people
  and by agents through `/api/docs`.
- Error messages name the service that caused them. Don't write "Google" where the provider is
  a variable.

## Known gaps

- **The CalDAV client has never met real iCloud.** It is written against RFC 4791/6578 and
  tested against a fake that reproduces the partition-host redirect, `403 valid-sync-token`, and
  a PUT with no ETag — but all of that is from the spec, not from observation. Treat a surprise
  from Apple as likely-our-bug.
- **Single process only.** `services/pushqueue.py` keeps the event loop in module globals, so
  more than one uvicorn worker would give you N racing pull loops on one SQLite file.
- **No retry ceiling.** A permanently failing push retries every `PUSH_INTERVAL_SECONDS` forever.
- **Editing one occurrence of a series is unsupported** on both providers; the UI edits the
  whole series. Cancelling a single iCloud occurrence does work.
- **The `.ics` feed token** is derived from `SECRET_KEY` and cannot be revoked or scoped
  individually.
