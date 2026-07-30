# Subscribing on phones, and Home Assistant

Family Calendar publishes a read-only iCalendar feed. That one feature does two jobs: family
members can subscribe on their phones without you setting up anything else, and Home Assistant
can pull the family schedule in with its built-in integration.

Find the links under **Settings → Sharing**.

> **The link is the password.** Anyone with the URL can read the family's schedule. It's the
> same model as Google Calendar's own "secret address in iCal format". Don't post it anywhere
> public. The token changes if you change `SECRET_KEY`, which is how you revoke it.

---

## Subscribing on a phone

There is a link for the whole family and one per calendar. Copy whichever you want and add it
as a **subscribed calendar** — not an import, which would be a one-time copy that never updates.

**iPhone / iPad**
Settings → Apps → Calendar → Accounts → Add Account → Other → **Add Subscribed Calendar** →
paste the link → Next → Save.

**Android**
Android's calendar app can't subscribe to a URL directly. Add it to Google Calendar on a
computer instead — [calendar.google.com](https://calendar.google.com) → Other calendars → **+**
→ **From URL** — and it syncs down to the phone. Note Google refreshes external feeds slowly,
often only every several hours; that's Google's behaviour, not ours.

**macOS Calendar**
File → New Calendar Subscription → paste → set *Auto-refresh* to every 5 minutes.

**Outlook**
Add calendar → Subscribe from web → paste.

The feed covers the last 90 days and the next year, and asks subscribers to refresh every
30 minutes.

---

## Home Assistant

Home Assistant's built-in **Remote Calendar** integration reads an ICS feed. On its own it
refreshes only **once every 24 hours**, which is useless for a family calendar — so this app
also pushes Home Assistant a "refresh now" whenever anything changes. Set up both halves and
you get a calendar entity that updates within a second of someone adding an event on the wall.

Nothing custom runs inside Home Assistant. There is no HACS component to install or maintain.

### 1. Add the calendar

1. In Home Assistant: **Settings → Devices & Services → Add Integration → Remote Calendar**
2. **Calendar name**: `Family Calendar`
3. **URL**: paste the link from Settings → Sharing → Everything
4. Submit. You should get an entity like `calendar.family_calendar`.

### 2. Turn off its 24-hour polling

Leaving it on is harmless but pointless, and it costs you a request a day.

1. Open the Remote Calendar integration → the entity → the gear icon
2. Turn off **Enable polling for updates**

### 3. Create a token for this app

In Home Assistant: click your user name (bottom left) → **Security** tab → scroll to
**Long-lived access tokens** → **Create token**. Copy it — it is shown only once.

### 4. Point this app at Home Assistant

Back in Family Calendar, **Settings → Sharing → Home Assistant**:

- **Home Assistant URL** — e.g. `http://homeassistant.local:8123`
- **Long-lived access token** — the token you just created
- **Calendar entity** — the entity id from step 1, e.g. `calendar.family_calendar`

Press **Test**. It should say it connected. Now add an event and watch the entity update
immediately.

### What you can do with it

```yaml
# Porch light on when someone's evening event ends
automation:
  - alias: "Light the porch after evening events"
    triggers:
      - trigger: calendar
        entity_id: calendar.family_calendar
        event: end
    conditions:
      - condition: sun
        after: sunset
    actions:
      - action: light.turn_on
        target:
          entity_id: light.porch
```

Calendar triggers support `event: start` and `event: end`, with an `offset` — so "15 minutes
before soccer practice" is a trigger, not a script.

### Troubleshooting

**The entity exists but has no events.** Check the URL includes `?token=...`. Open it in a
browser: you should get a text file starting with `BEGIN:VCALENDAR`.

**Home Assistant says the calendar is invalid.** Make sure you copied the whole link,
including the token. If you changed `SECRET_KEY` since copying it, the old link is dead — copy
the new one.

**Events appear but never update.** The push isn't reaching Home Assistant. Press **Test** in
Settings → Sharing. A common cause is the URL: it needs the scheme and port,
`http://homeassistant.local:8123`, not just the hostname.

**The whole thing is one-way.** Editing an event in Home Assistant will not write back here.
Remote Calendar is read-only by design. Use this app, or Google, to make changes.

---

## Why not a custom Home Assistant integration?

A HACS integration would allow editing from inside Home Assistant, but it costs roughly a day
per quarter forever: Home Assistant ships breaking changes monthly, deprecations run on about a
six-month clock, and any bug gets reported against "the custom integration" first. The feed
plus a push gets most of the value for none of that maintenance, and it can't break when Home
Assistant updates.

If there's demand for two-way editing later, the better first target is **to-do entities** for
the shopping lists rather than the calendar — Home Assistant's voice assistant has built-in
to-do intents, so "add milk to the shopping list" would write straight into this app.
