# Connecting Google Calendar

Family Calendar works fine with no Google setup at all — it just runs as a local calendar.
Follow this guide when you want events to sync both ways with Gmail or Google Workspace
accounts.

You do this **once for the whole household**. Each family member then clicks a button in the
app and signs in with their own Google account.

**Time needed:** about 10 minutes.

> **You can do all of this inside the app.** Open **Settings → Google** and expand *How to get a
> Client ID and secret from Google* — it has these same steps, with clickable links, the exact
> redirect URI for your installation ready to copy, and boxes to paste the credentials into.
> This page is the same walkthrough in longer form, if you would rather read it first.

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

Google reorganised this area of the console: what used to be **APIs & Services → OAuth consent
screen** is now the **Google Auth Platform**, split into Overview, Branding, Audience, Data
Access and Clients. Old links redirect there.

1. Go to <https://console.cloud.google.com/auth/overview> and click **Get started**.
2. **App name**: `Family Calendar`. **User support email**: your email.
3. **Audience**: choose **External**.
   (**Internal** only appears — and is the better choice — if you have Google Workspace and
   everyone uses the same workspace domain. Internal apps have no 7-day expiry and no
   publishing step, so you can skip Step 4.)
4. **Contact information**: your email again. Agree to the policy and click **Create**.

You do not need to add scopes. The app requests calendar access at sign-in time.

## Step 4 — Publish the app

**This is the step people skip, and it is the one that causes the most grief.**

A new app starts in **Testing**, and in Testing mode Google **expires every authorization after
7 days** — your whole family would have to reconnect once a week, forever. Testing mode also
caps you at 100 test users, and only addresses you have explicitly listed can connect at all.

1. Go to <https://console.cloud.google.com/auth/audience>.
2. Under **Publishing status** it will say **Testing**. Click **Publish app** and confirm.
3. Check it now reads **In production**.

**Publishing does not submit your app for review.** Verification is only required for apps
requesting sensitive scopes from the general public; a calendar app used by your own household
is not that, and nothing is listed anywhere — the app stays private to whoever you give the URL
to. There is no cost and no waiting.

Your family will still see a "Google hasn't verified this app" warning the first time they
connect — that is expected for a self-hosted app. They click **Advanced → Go to Family Calendar
(unsafe)** to continue. It is your own app; the warning simply means you haven't paid for a
formal review.

If you would rather stay in Testing mode, you must add each family member's Google address
under **Test users** on that same Audience page, and accept that everyone reconnects weekly.

## Step 5 — Create the OAuth client

1. Go to <https://console.cloud.google.com/auth/clients>.
2. Click **Create client**.
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

## Step 6 — Paste the credentials into the app

Open **Settings → Google** in Family Calendar. No file editing, and no restart.

1. **This app's address** — how your family reaches the app, e.g. `http://192.168.1.50:8080`.
   It must match what you registered in Step 5. The page shows the resulting **Redirect URI**
   right underneath, with a copy button, so you can check the two agree.
2. **Client ID** and **Client secret** — paste both from the Google dialog.

They save as you leave each box. The secret is encrypted with your `SECRET_KEY` and is never
readable back out of the app.

> If you haven't set a real `SECRET_KEY` in `.env` yet, do it now, before connecting anyone —
> it's the key your Google credentials and everyone's tokens are encrypted with. See
> [configuration.md](configuration.md).

## Step 7 — Each person connects their email

Still on **Settings → Google**, under **Connect an email**, every family member gets a row:

1. Press **Connect an email** next to your name and sign in with your Google account.
2. Google warns that the app isn't verified — that's expected for something you host yourself.
   Choose **Advanced** → **Go to Family Calendar**.
3. You land back in the app with your calendars discovered.

Anyone can connect **as many accounts as they like** — press **Add another** for a work
Workspace account alongside a personal Gmail. Each connected email's calendars appear in the
**Calendars** section below, where you choose who each one belongs to and switch **Syncing** on
for the ones you want on the wall.

---

## Troubleshooting

**`redirect_uri_mismatch`**
The URI in Google Cloud doesn't exactly match the **Redirect URI** shown in Settings → Google.
Copy it from there with the copy button and compare character by character — a missing port,
`https` vs `http`, or a trailing slash are the usual culprits. Changes in Google Cloud can take
a few minutes to take effect.

**"Google hasn't verified this app"**
Expected for a self-hosted app. Click **Advanced → Go to Family Calendar (unsafe)**.

**An account shows "Needs reconnecting" — especially about a week after setup**
The refresh token was revoked or expired. The usual cause is by far the most common problem
with this whole setup: the OAuth app is still in **Testing** mode, where Google expires every
authorization after 7 days. Check
<https://console.cloud.google.com/auth/audience> — if the publishing status says *Testing*,
press **Publish app** (Step 4), then reconnect each account from Settings → Google. Once it
says *In production*, connections last indefinitely.

**`access_denied` when connecting**
The Google account isn't on the test-user list and the app is still in Testing mode. Publish the
app (Step 4), or add them as a test user under **Audience → Test users**.

**Calendars appear but no events**
Make sure **Syncing** is switched on for that calendar in Settings → Google, then click
**Sync now**. Check `GET /api/sync/status` for a specific error message.

**Events sync from Google but my edits don't go back**
Check the calendar isn't read-only. Subscribed calendars (holidays, someone else's shared
calendar) can't be edited — those show `read-only` next to their name.
