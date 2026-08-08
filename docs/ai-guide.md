# Mantel — API guide for AI agents

You are talking to a self-hosted family calendar that runs on a home network.
**There is no authentication.** Every action the touchscreen UI can perform is available here.

- Base URL: the host serving the UI, plus `/api` — e.g. `http://localhost:8080/api`
- Full machine-readable schema: `GET /api/openapi.json`
- Interactive docs: `/api/docs`

## The model in one paragraph

**Users** are family members; each has a name and a color. A user links one or more
**accounts** — Google or iCloud, as many of each as they like. Each account exposes
**calendars**, which a user *claims* — claiming is what makes a calendar visible and gives its
events that person's color. **Events** live on a calendar. Events on Google- and iCloud-backed
calendars sync both ways automatically; events on local calendars stay in this app. There is
also a **dashboard** of widgets for the wall display.

Which service a calendar came from is `account_provider`: `"google"`, `"icloud"`, or `null` for
a calendar that exists only here. An event's `origin` is the same three values. **You rarely
need to branch on it** — the one place it genuinely matters is repeating events, below.

## Conventions

- Timestamps are ISO-8601 with an offset: `2026-08-03T17:00:00Z`. Send any offset you like;
  responses are always UTC.
- All-day events use UTC midnight boundaries with an **exclusive end**. An event on Aug 1–2
  is `start_at=2026-08-01T00:00:00Z`, `end_at=2026-08-03T00:00:00Z`.
- Errors always return `{"error": {"code": "...", "message": "..."}}` — check `code`, show `message`.
- Query events by date range. There is no pagination.
- `PATCH` bodies are partial: send only what changes.

## Common tasks

### 1. See what's happening this week

```http
GET /api/events?start=2026-08-02T00:00:00Z&end=2026-08-09T00:00:00Z
```

```json
[
  {
    "id": 12,
    "calendar_id": 1,
    "calendar_name": "Family",
    "color": "#3b82f6",
    "user_id": 1,
    "title": "Soccer practice",
    "location": "Riverside Park",
    "start_at": "2026-08-03T17:00:00Z",
    "end_at": "2026-08-03T18:30:00Z",
    "all_day": false,
    "origin": "local",
    "sync_state": "synced",
    "editable": true
  }
]
```

Every event carries its display `color` and the `user_id` of the calendar's owner, so you never
need a second request to work out whose event it is. An event is returned if it *overlaps* the
range at all.

Useful filters: `&user_ids=1,2`, `&calendar_ids=3`, `&q=dentist`.

### 2. Find out who is in the family and which calendars they own

```http
GET /api/users
GET /api/calendars?claimed=true
```

Use `GET /api/calendars` to pick a `calendar_id` before creating anything. Only calendars with
`"writable": true` accept new events.

### 3. Add an event

```http
POST /api/events
Content-Type: application/json

{
  "calendar_id": 1,
  "title": "Dentist",
  "location": "Main St",
  "start_at": "2026-08-05T14:00:00Z",
  "end_at": "2026-08-05T15:00:00Z"
}
```

Returns `201` with the created event. If the calendar is backed by Google or iCloud the
response has `"sync_state": "pending_create"` — the event is already saved and will reach the
service within seconds. Do not poll or retry.

### 4. Move or rename an event

```http
PATCH /api/events/12
{ "start_at": "2026-08-05T15:00:00Z", "end_at": "2026-08-05T16:00:00Z" }
```

### 5. Delete an event

```http
DELETE /api/events/12
```

Returns `204`. For a synced calendar the event is removed from Google or iCloud too.

### 6. Add an all-day event

```http
POST /api/events
{
  "calendar_id": 1,
  "title": "Beach trip",
  "all_day": true,
  "start_at": "2026-08-01T00:00:00Z",
  "end_at": "2026-08-03T00:00:00Z"
}
```

That covers August 1 and 2.

### 6b. Make an event repeat

```http
POST /api/events
{
  "calendar_id": 1,
  "title": "Piano lesson",
  "start_at": "2026-08-03T17:00:00Z",
  "end_at": "2026-08-03T18:00:00Z",
  "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO,WE"
}
```

`recurrence_rule` is an iCalendar RRULE **without** the `RRULE:` prefix. `FREQ` must be
`DAILY`, `WEEKLY`, `MONTHLY` or `YEARLY`; `INTERVAL`, `BYDAY`, `COUNT` and `UNTIL` all work.

A repeating event is stored **once**. `GET /api/events` returns one entry per occurrence in
the range, and every occurrence carries the same `id` — the id of the series. So `PATCH`ing
that id changes the whole series, not one occurrence.

Responses also include `recurrence_text`, a ready-to-display phrasing like
`"Every week on Mon, Wed"`.

### 6c. Connect an iCloud account

The one linking flow you can drive end to end. Google needs a browser for OAuth; Apple does
not, because there is no OAuth for iCloud calendars.

```http
POST /api/accounts/icloud
{
  "user_id": 1,
  "apple_id": "someone@icloud.com",
  "app_password": "abcd-efgh-ijkl-mnop"
}
```

`app_password` is an **app-specific password** the person generates at appleid.apple.com under
Sign-In and Security. It is not their Apple ID password, and asking for that one instead will
simply fail. Whitespace is stripped; the dashes are part of it.

The credential is checked against iCloud before anything is stored, so the response is
trustworthy:

- `201` — linked. The account's calendars are discovered in the same call.
- `400` — the password was rejected, or was empty. **Nothing is stored**; there is no
  half-linked account to clean up. Show the message and ask for a new password.
- `502` — iCloud was unreachable. This is *not* a bad password. Retry later rather than
  telling anybody to regenerate anything.
- `404` — no such `user_id`.

Posting again for the same Apple ID replaces the stored password, which is how an account that
went stale is repaired. Discovered calendars arrive **unclaimed with syncing off** — nothing
reaches the wall display until somebody opts in, so expect to follow up with
`PATCH /api/calendars/{id}` setting `claimed_by_user_id` and `sync_enabled`.

### 7. Put something on the dashboard

```http
GET  /api/dashboard/widget-types      # discover what's available and what config each takes
POST /api/dashboard/widgets
{ "widget_type": "upcoming_events", "size": "medium", "config": { "days": 3 } }
```

Sizes are `small`, `medium`, `large`. Reorder with `PATCH /api/dashboard/widgets/{id}` and a
new `position`.

## Things that will trip you up

- **Read-only calendars return 403.** Holidays, shared subscriptions and calendars somebody
  shared without edit rights are read-only, on both services. Check `"writable"` on the
  calendar, or `"editable"` on the event, first. The error message names the service.
- **`end_at` must be after `start_at`** — otherwise `400 bad_request`.
- **Unclaimed calendars are dim grey** and generally not shown on the wall. Claim one by setting
  `claimed_by_user_id` via `PATCH /api/calendars/{id}`.
- **Moving an event between calendars is not supported yet.** Delete and recreate instead.
- **Repeating events behave in two different ways, and the difference is the provider.**
  This is the one place `origin` matters, and getting it wrong edits more than you meant to.

  | | `origin: "local"` or `"icloud"` | `origin: "google"` |
  | --- | --- | --- |
  | Stored as | one row, the series | one row per occurrence |
  | `recurrence_rule` | set | `null` (`recurring: true`) |
  | `id` on each occurrence | the same — the series' id | different for each |
  | `PATCH` that id | changes **the whole series** | changes **that occurrence only** |
  | `DELETE` that id | deletes **the whole series** | deletes **that occurrence only** |

  Google is asked to expand its own series, so it sends instances. iCloud sends the rule and
  this app expands it, exactly as it does for its own calendars. **Check `recurrence_rule`
  before editing a `recurring` event**: if it is set, you are holding the series.

- **A single occurrence of an iCloud series can be cancelled but not edited.** `DELETE` on an
  occurrence that iCloud has already singled out (one somebody moved on their phone) removes
  just that occurrence. There is no way to change one occurrence of a series from the API on
  either service — that is a UI limitation, not a transport one.
- **`user_ids` filters by person**, not by calendar: it matches whoever claimed the calendar an
  event lives on.

## Everything else

| Group     | Endpoints                                                                     |
| --------- | ----------------------------------------------------------------------------- |
| Meta      | `GET /api/version`, `/api/health`, `/api/ai-guide`                            |
| Users     | `GET/POST /api/users`, `GET/PATCH/DELETE /api/users/{id}`                     |
| Accounts  | `GET /api/accounts`, `GET /api/accounts/google/auth-url?user_id=`, `POST /api/accounts/icloud`, `DELETE /api/accounts/{id}` |
| Calendars | `GET/POST /api/calendars`, `GET/PATCH/DELETE /api/calendars/{id}`             |
| Events    | `GET/POST /api/events`, `GET/PATCH/DELETE /api/events/{id}`                   |
| Dashboard | `GET /api/dashboard/widget-types`, `GET/POST /api/dashboard/widgets`, `PATCH/DELETE /api/dashboard/widgets/{id}` |
| Photos    | `GET/POST /api/photos`, `GET /api/photos/{id}/file`, `DELETE /api/photos/{id}` |
| Weather   | `GET /api/weather`, `GET /api/weather/search?q=`                              |
| Lists     | `GET/POST /api/lists`, `GET/PATCH/DELETE /api/lists/{id}`, `POST /api/lists/{id}/items`, `PATCH/DELETE /api/lists/{id}/items/{item_id}`, `POST /api/lists/{id}/clear-checked` |
| Feeds     | `GET /api/feeds/token`, `GET /api/feeds/all.ics?token=`, `GET /api/feeds/{calendar_id}.ics?token=` |
| Sync      | `GET /api/sync/status`, `POST /api/sync/run`, `POST /api/sync/calendars`      |
| Settings  | `GET/PATCH /api/settings`                                                     |

Photos are screensaver images. `POST /api/photos` takes multipart form-data under `file` and
accepts JPEG, PNG or WebP; anything that isn't a decodable image is rejected regardless of its
filename or declared content type.

Lists are shared by the whole household — there are no private lists. `GET /api/lists` returns
each list with its items already sorted (unchecked first). Adding to a grocery list is one
call:

```http
POST /api/lists/1/items
{ "text": "Milk" }
```

`GET /api/weather` never returns an error status. Check `available`; when it is false, `reason`
explains why. `stale: true` means the upstream service was unreachable and the data came from
cache — still worth displaying.

The `/api/feeds/*.ics` endpoints are the only ones that require a credential — the token from
`GET /api/feeds/token` — because a feed URL is the one thing likely to be pasted into a service
outside the house. Everything else is open on the LAN.

`GET/PATCH /api/settings` is where Google, weather, screensaver and Home Assistant
configuration lives — there is no config file to edit. Secrets (`google_client_secret`,
`ha_token`) are write-only: PATCH accepts them, GET always returns `""` and reports only
whether one is set under `server.google_client_secret_set` / `server.ha_token_set`. Sending an
empty string leaves a stored secret unchanged.

**iCloud has no settings at all** — no client id, no secret, no redirect URI. An Apple ID is
either linked or it is not, which `server.icloud_linked` and `GET /api/sync/status` report.

`GET /api/version` is also how screens detect a new deployment — they poll it and hard-reload
when the version changes.
