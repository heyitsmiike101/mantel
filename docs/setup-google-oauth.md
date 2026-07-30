# Connecting Google Calendar

Family Calendar works fine with no Google setup at all — it just runs as a local calendar.
Follow this guide when you want events to sync both ways with Gmail or Google Workspace
accounts.

You do this **once for the whole household**. Each family member then clicks a button in the
app and signs in with their own Google account.

**Time needed:** about 10 minutes.

---

## Step 1 — Create a Google Cloud project

1. Go to <https://console.cloud.google.com/>.
2. Click the project dropdown in the top bar, then **New Project**.
3. Name it something like `Family Calendar` and click **Create**.
4. Make sure the new project is selected in the top bar before continuing.

There is no cost. The Calendar API usage of a single family is far inside the free tier.

## Step 2 — Turn on the Google Calendar API

1. In the left menu go to **APIs & Services → Library**.
2. Search for **Google Calendar API**.
3. Click it, then click **Enable**.

## Step 3 — Configure the consent screen

This is the screen your family sees when they connect their account.

1. Go to **APIs & Services → OAuth consent screen**.
2. Choose **External**, then **Create**.
   (**Internal** only appears — and is the better choice — if you have Google Workspace and
   everyone uses the same workspace domain.)
3. Fill in:
   - **App name**: `Family Calendar`
   - **User support email**: your email
   - **Developer contact email**: your email
4. Click **Save and Continue** through the Scopes screen — you do not need to add scopes here.
5. On **Test users**, click **Add Users** and add the Google address of every family member who
   will connect an account. Then **Save and Continue**.

### Important: publish the app

While the app is in **Testing** mode, Google **expires refresh tokens after 7 days**, which
means everyone has to reconnect weekly. To avoid that:

1. Go back to **OAuth consent screen**.
2. Click **Publish App**, then confirm.

Publishing an app that only requests calendar access for its own users does not require
Google's verification review. Your family will see an "Google hasn't verified this app" warning
the first time they connect — that is expected for a self-hosted app. They click **Advanced →
Go to Family Calendar (unsafe)** to continue. It is your own app; that warning simply means you
haven't paid for a formal review.

## Step 4 — Create the OAuth client

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. **Application type**: `Web application`.
4. **Name**: `Family Calendar`.
5. Under **Authorized redirect URIs**, click **Add URI** and enter your app's address followed
   by `/api/accounts/google/callback`. It must match **exactly**, including the port:

   | How you reach the app          | Redirect URI to add                                        |
   | ------------------------------ | ---------------------------------------------------------- |
   | `http://localhost:8080`        | `http://localhost:8080/api/accounts/google/callback`        |
   | `http://192.168.1.50:8080`     | `http://192.168.1.50:8080/api/accounts/google/callback`     |
   | `http://calendar.local:8080`   | `http://calendar.local:8080/api/accounts/google/callback`   |

   Add more than one if people reach the app different ways. Google allows plain `http` for
   `localhost`; for a LAN IP or hostname it is also accepted for this kind of app.

6. Click **Create**. Google shows your **Client ID** and **Client secret** — keep this dialog
   open for the next step.

## Step 5 — Put the credentials in your `.env`

In the folder where you cloned Family Calendar:

```bash
cp .env.example .env
```

Then edit `.env` and set:

```
PUBLIC_BASE_URL=http://192.168.1.50:8080
GOOGLE_CLIENT_ID=1234567890-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
```

`PUBLIC_BASE_URL` must be the same address you registered in Step 5 — this is what the app
tells Google to redirect back to.

While you're here, set a real `SECRET_KEY`. It encrypts the stored Google tokens:

```bash
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"
```

Paste the output as `SECRET_KEY`.

## Step 6 — Restart and connect

```bash
./run.sh
```

Then in the app:

1. Go to **Settings → Google**.
2. Pick which family member the account belongs to.
3. Click **Connect a Google account** and sign in.
4. Back in the app, go to the calendar list, choose who owns each calendar, and switch **Syncing**
   on for the ones you want on the wall.

Repeat for each family member and each of their Google accounts. One person can link as many
accounts as they want (personal Gmail plus a work Workspace account, for example).

---

## Troubleshooting

**`redirect_uri_mismatch`**
The URI in Google Cloud doesn't exactly match `PUBLIC_BASE_URL` + `/api/accounts/google/callback`.
Check for a missing port, `https` vs `http`, or a trailing slash. Changes in Google Cloud can
take a few minutes to take effect.

**"Google hasn't verified this app"**
Expected for a self-hosted app. Click **Advanced → Go to Family Calendar (unsafe)**.

**An account shows "Needs reconnecting"**
The refresh token was revoked or expired. The usual cause is leaving the OAuth app in
**Testing** mode, where Google expires tokens after 7 days — see Step 3. Reconnect the account
from Settings → Google.

**`access_denied` when connecting**
The Google account isn't on the test-user list and the app is still in Testing mode. Either add
them as a test user or publish the app.

**Calendars appear but no events**
Make sure **Syncing** is switched on for that calendar in Settings → Google, then click
**Sync now**. Check `GET /api/sync/status` for a specific error message.

**Events sync from Google but my edits don't go back**
Check the calendar isn't read-only. Subscribed calendars (holidays, someone else's shared
calendar) can't be edited — those show `read-only` next to their name.
