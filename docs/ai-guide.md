# Family Calendar — API guide for AI agents

You are talking to a self-hosted family calendar that runs on a home network.
**There is no authentication.** Every action the touchscreen UI can perform is available here.

- Base URL: the host serving the UI, plus `/api` — e.g. `http://localhost:8080/api`
- Full machine-readable schema: `GET /api/openapi.json`
- Interactive docs: `/api/docs`

## The model in one paragraph

**Users** are family members; each has a name and a color. A user links one or more Google
**accounts**. Each account exposes **calendars**, which a user *claims* — claiming is what makes
a calendar visible and gives its events that person's color. **Events** live on a calendar. Events
on Google-backed calendars sync both ways automatically; events on local calendars stay in
this app. There is also a **dashboard** of widgets for the wall display.

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

Returns `201` with the created event. If the calendar is Google-backed the response has
`"sync_state": "pending_create"` — the event is already saved and will reach Google within
seconds. Do not poll or retry.

### 4. Move or rename an event

```http
PATCH /api/events/12
{ "start_at": "2026-08-05T15:00:00Z", "end_at": "2026-08-05T16:00:00Z" }
```

### 5. Delete an event

```http
DELETE /api/events/12
```

Returns `204`. For Google calendars the event is removed from Google too.

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

### 7. Put something on the dashboard

```http
GET  /api/dashboard/widget-types      # discover what's available and what config each takes
POST /api/dashboard/widgets
{ "widget_type": "upcoming_events", "size": "medium", "config": { "days": 3 } }
```

Sizes are `small`, `medium`, `large`. Reorder with `PATCH /api/dashboard/widgets/{id}` and a
new `position`.

## Things that will trip you up

- **Read-only calendars return 403.** Some Google calendars (holidays, shared subscriptions) are
  subscribed read-only. Check `"writable"` on the calendar, or `"editable"` on the event, first.
- **`end_at` must be after `start_at`** — otherwise `400 bad_request`.
- **Unclaimed calendars are dim grey** and generally not shown on the wall. Claim one by setting
  `claimed_by_user_id` via `PATCH /api/calendars/{id}`.
- **Moving an event between calendars is not supported yet.** Delete and recreate instead.
- **Two kinds of repeating event exist.** Ones this app owns have a `recurrence_rule`, are
  stored once, and every returned occurrence shares the series' `id` — editing it edits the
  whole series. Ones that came from Google arrive already expanded, with `recurrence_rule:
  null` and `recurring: true`; each is a separate row, so editing one changes only that
  occurrence.
- **`user_ids` filters by person**, not by calendar: it matches whoever claimed the calendar an
  event lives on.

## Everything else

| Group     | Endpoints                                                                     |
| --------- | ----------------------------------------------------------------------------- |
| Meta      | `GET /api/version`, `/api/health`, `/api/ai-guide`                            |
| Users     | `GET/POST /api/users`, `GET/PATCH/DELETE /api/users/{id}`                     |
| Accounts  | `GET /api/accounts`, `GET /api/accounts/google/auth-url?user_id=`, `DELETE /api/accounts/{id}` |
| Calendars | `GET/POST /api/calendars`, `GET/PATCH/DELETE /api/calendars/{id}`             |
| Events    | `GET/POST /api/events`, `GET/PATCH/DELETE /api/events/{id}`                   |
| Dashboard | `GET /api/dashboard/widget-types`, `GET/POST /api/dashboard/widgets`, `PATCH/DELETE /api/dashboard/widgets/{id}` |
| Photos    | `GET/POST /api/photos`, `GET /api/photos/{id}/file`, `DELETE /api/photos/{id}` |
| Weather   | `GET /api/weather`, `GET /api/weather/search?q=`                              |
| Lists     | `GET/POST /api/lists`, `GET/PATCH/DELETE /api/lists/{id}`, `POST /api/lists/{id}/items`, `PATCH/DELETE /api/lists/{id}/items/{item_id}`, `POST /api/lists/{id}/clear-checked` |
| Feeds     | `GET /api/feeds/token`, `GET /api/feeds/all.ics?token=`, `GET /api/feeds/{calendar_id}.ics?token=` |
| Sync      | `GET /api/sync/status`, `POST /api/sync/run`                                  |
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

`GET /api/version` is also how screens detect a new deployment — they poll it and hard-reload
when the version changes.
