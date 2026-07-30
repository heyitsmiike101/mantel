# Changelog

## 0.1.0

First release.

- Today, 3-day, week and month calendar views, built for touch in portrait and landscape
- Family members with per-person colors; each can link multiple Google accounts and claim
  the calendars they own
- Two-way Google Calendar sync with incremental pulls, an automatic push queue, and
  last-write-wins conflict handling
- Customizable dashboard wall: upcoming events, today by person, clock, mini month, and a
  shared family note
- Screens hard-reload themselves when a new version is deployed; the version is always visible
- Full REST API with OpenAPI docs and a guide written for AI agents at `/api/ai-guide`
- Single Docker container, SQLite in WAL mode, no login
