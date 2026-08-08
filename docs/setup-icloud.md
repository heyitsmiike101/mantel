# Connecting iCloud

Two-way sync with Apple Calendar, so an event added on the wall display shows up on
everyone's iPhone within seconds, and an event added on a phone reaches the wall at
the next sync.

**This is much shorter than the Google setup.** There is no developer account, no
client ID or secret, no redirect URI, and none of the LAN-address trouble that makes
[setup-google-oauth.md](setup-google-oauth.md) as long as it is. Each person needs one
app-specific password, which takes about a minute.

## Why a password and not a sign-in button

Apple does not offer OAuth for calendars. The only supported way for a third-party app
to reach iCloud Calendar is **CalDAV**, authenticated with an Apple ID and an
*app-specific password* — a password Apple generates that works for exactly one app and
can be cancelled on its own without touching your real one.

The practical differences from Google:

| | Google | iCloud |
|---|---|---|
| Household setup | ~10 minutes in Google Cloud | none |
| Each person | Sign-in button | Apple ID + app-specific password |
| Expires on its own | Yes, after 7 days in Testing mode | No |
| Revoke from this app | Yes, on unlink | No — do it at appleid.apple.com |

## Steps

1. **Turn on two-factor authentication** for the Apple ID, if it isn't already. Apple
   only offers app-specific passwords on accounts that have it.

2. Go to **[appleid.apple.com](https://appleid.apple.com)** and sign in.

3. Under **Sign-In and Security**, open **App-Specific Passwords**.

4. Press **+**, give it a name you'll recognise later — "Mantel" — and Apple shows you a
   password in four groups, like `abcd-efgh-ijkl-mnop`.

   **It is only shown once.** If you lose it, delete it and make another; there is no way
   to look it up again.

5. In Mantel, open **Settings → Apple**, press **Connect an Apple ID** next to the right
   person, and paste the Apple ID and the password.

   The password is checked against iCloud before anything is saved, so if it's wrong
   you'll know immediately rather than finding out from a sync that quietly never works.
   Stray spaces are ignored; the dashes are part of the password, so leave them in.

6. Open **Settings → Calendars** to pick which calendars to show and who each one
   belongs to. **They all arrive switched off**, so nothing lands on the wall display
   until you say so.

## Afterwards

**Where the password lives.** Encrypted at rest with your `SECRET_KEY`, in the app's
database. It is never sent back to the browser and never appears in the API. Rotating
`SECRET_KEY` makes it unreadable, which shows up as the account needing to be connected
again.

**Taking access away.** Unlinking in Settings removes the calendars and their events
from this app, but it cannot cancel the password — only Apple can. Delete it on the
App-Specific Passwords page if you want it gone for good.

**Changing your Apple ID password cancels every app-specific password**, including this
one. That is Apple's behaviour, not a bug here. The account will show as needing to be
connected again; make a new app-specific password and connect it.

**Read-only calendars.** A calendar somebody shared with you without edit rights is
marked read-only, and this app won't let you create or change events on it. That is
reported by iCloud, not decided here.

## Repeating events

Apple sends a repeating event as one item with its rule, and Mantel expands it locally —
the same as it does for a calendar that only exists in this app. If somebody moves or
cancels a single occurrence on their phone, that arrives too, and the wall display shows
the series with that one week moved or gone.

What isn't supported is editing *one occurrence* of a series **from Mantel** — editing a
repeating event here changes the whole series. That has always been true of Google sync
too.

## Troubleshooting

**"iCloud rejected the app-specific password."**
The usual causes, in order: the password was mistyped, it was cancelled at
appleid.apple.com, or the Apple ID password was changed since it was made. Make a fresh
one and connect again.

**No calendars appeared after connecting.**
Open **Settings → Calendars** and press **Check for new calendars**. Reminders lists are
deliberately not offered — they can't hold an event.

**Nothing syncs, but the account says it's connected.**
Check that the calendar has **Syncing** switched on in Settings → Calendars. Calendars
arrive switched off on purpose.

**An event I made here hasn't reached my phone.**
Pushes are attempted within seconds and retried on a timer. Settings → Apple shows how
many changes are still waiting; Settings → Calendars shows the last error against the
calendar it happened on.

## See also

- [configuration.md](configuration.md) — what's set where
- [sharing-and-home-assistant.md](sharing-and-home-assistant.md) — read-only feeds, which
  are a different thing from this
