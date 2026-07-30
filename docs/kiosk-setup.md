# Setting up a wall display

Family Calendar is a web page, so anything with a browser can be the wall display: a Raspberry
Pi behind a monitor, an old Android tablet, a retired iPad. This guide covers getting one into
full-screen kiosk mode and, crucially, getting the **screen to turn off at night** — which the
browser cannot do for you.

Before you start, decide which route the display should sit on. `/dashboard` and
`/calendar/week` are the usual choices.

> **The app updates itself.** Every screen polls for new versions and hard-reloads on its own,
> so you never need to touch a mounted tablet after a deploy. That's the whole reason the
> version number is in the corner.

---

## Raspberry Pi + monitor

The best option for a 24–32" display. No battery to swell, and you can turn the screen off
properly.

**A Pi 4 or Pi 5 is recommended.** A Pi 3 works but is sluggish. You can run the container on
the Pi itself, or run it on a NAS/server elsewhere and let the Pi be a dumb browser — the
second option is lighter and means an SD card failure costs you nothing.

### 1. Chromium in kiosk mode

On Raspberry Pi OS with desktop, create `~/.config/autostart/familycalendar.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Family Calendar
Exec=chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --check-for-update-interval=31536000 --app=http://YOUR-SERVER:8080/dashboard
X-GNOME-Autostart-enabled=true
```

Replace `YOUR-SERVER` with the machine running the container. Useful extras:

- `--disable-features=Translate` stops the translate bar appearing
- `--hide-scrollbars` for a cleaner look
- If the Pi shows a black screen on boot, `--disable-gpu` is the usual fix

Stop the Pi blanking the screen on its own — in `~/.config/wayfire.ini`:

```ini
[idle]
dpms_timeout = -1
screensaver_timeout = -1
```

(Use `xset s off -dpms` in your autostart instead if you're on the older X11 session.)

### 2. Turning the screen off at night

**This is the part every stale tutorial gets wrong.** `vcgencmd display_power 0` **no longer
works** on Raspberry Pi OS Bookworm or newer. It was an X11/legacy-stack command and Bookworm
moved to Wayland.

What actually works, in order of preference:

| Your setup | Off | On |
|---|---|---|
| **Wayland** (Bookworm+, the default) | `wlopm --off '*'` | `wlopm --on '*'` |
| Wayland, no `wlopm` | `wlr-randr --output HDMI-A-1 --off` | `wlr-randr --output HDMI-A-1 --on` |
| X11 (Bullseye or older) | `xrandr --output HDMI-1 --off` | `xrandr --output HDMI-1 --auto` |
| TV over HDMI | `echo "standby 0" \| cec-client -s -d 1` | `echo "on 0" \| cec-client -s -d 1` |

Install with `sudo apt install wlopm` (Raspberry Pi OS Bookworm/Trixie and Debian 13; **not**
available on plain Debian 12).

Prefer `wlopm` over `wlr-randr`: `wlr-randr` removes the output from the compositor layout
entirely, so the display can come back with the wrong resolution or rotation and you'll need to
pass `--mode`/`--transform` on wake. `wlopm` uses the Wayland power-management protocol and
leaves the layout intact.

**Gotcha:** these commands need `WAYLAND_DISPLAY` set. If a cron job or script can't find the
socket, the screen flickers off and comes straight back a few seconds later. Set it explicitly:

```bash
export WAYLAND_DISPLAY=wayland-1
export XDG_RUNTIME_DIR=/run/user/1000
```

Schedule it with `crontab -e`:

```cron
0 23 * * * WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000 wlopm --off '*'
30 6 * * * WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000 wlopm --on '*'
```

If the screen turns off and immediately wakes, the usual culprit is a monitor with automatic
input scanning re-detecting the signal. Disable auto-input-select in the monitor's own menu.

### 3. Wi-Fi power saving

Pi Wi-Fi can idle-disconnect and leave the display stale. Turn it off:

```bash
sudo iw wlan0 set power_save off
```

Make it stick by adding that line to `/etc/rc.local` before `exit 0`.

---

## Android tablet

The cheapest route. A tablet you already own, a wall mount, and a USB cable.

Use **[Fully Kiosk Browser](https://www.fully-kiosk.com/)** rather than Chrome — it exists
precisely for this. The free version covers what you need here: full screen, no address bar,
`Start URL`, and motion-triggered screen wake. Its screen on/off scheduling and remote admin
sit behind the one-time Plus licence (about $7).

Settings worth changing:

- **Web Content Settings → Start URL**: your display route
- **Web Auto Reload**: leave *off*. The app already reloads itself on new versions, and
  Fully's reload would fight the screensaver.
- **Device Management → Keep Screen On**: on
- **Screensaver**: turn Fully's own screensaver *off* and use the app's, so photos and the
  sleep window are managed in one place
- **Advanced Web Settings → Enable Fullscreen Mode**

Newer Android is *more* aggressive about power management, not less. If the browser freezes
overnight, that's Android suspending the app — turn off battery optimisation for Fully
specifically.

### Battery swelling — read this one

**A permanently charging tablet on a wall is the single most common hardware failure in this
whole category.** Lithium cells held at 100% and warm will swell, and a swollen battery can
crack the screen or worse.

Options, best first:

1. **Charge cycling** — put the charger on a smart plug and cycle it between roughly 40% and
   80%. Any home-automation setup can do this from the tablet's battery level.
2. **Vendor charge limits** — some Samsung and Lenovo tablets can cap charging at 85% in
   settings. Use it if you have it.
3. **Battery delete** — for a permanently mounted tablet, running from USB with the battery
   removed is the durable answer. It needs a capacitor-and-diode mod on many devices to boot
   without a cell present. Search for your specific model first.

Check a wall tablet's back panel every few months. If it's bulging or the screen is lifting at
an edge, stop charging it and replace the battery.

---

## iPad / iPhone

No Fully Kiosk on iOS, so the setup is simpler but less controllable.

1. Open the display route in Safari
2. **Share → Add to Home Screen** — this launches without Safari's chrome, which is as close to
   kiosk mode as iOS offers
3. **Settings → Display & Brightness → Auto-Lock → Never**
4. **Settings → Accessibility → Guided Access** locks it to the one app so a passerby can't
   navigate away — triple-click the side button to start a session

Once we ship the PWA manifest (v0.2.0), the home-screen app also gets an icon and works offline.

Old iPads are a real option, but Safari on iOS 12 and earlier will struggle with a modern
JavaScript app. iOS 15+ is a safe floor.

---

## Any other screen

An old laptop, a Fire tablet, a spare monitor on a mini PC — all fine. The requirements are
only:

- A browser from roughly the last five years
- The screen stays awake (disable OS sleep and screensaver)
- Network access to whichever machine runs the container

---

## Recommended app settings for a wall display

In **Settings → Display**:

- **Text size: wall** — scales text *and* the hour rows so a 5-minute gap is still tappable
  from across the room
- **Day starts / ends** — trim to the hours your family actually uses so the grid isn't mostly
  empty
- **Week starts on** — whichever matches the paper calendar you're replacing

---

## Troubleshooting

**Screen turns off, then comes straight back on.** Either `WAYLAND_DISPLAY` isn't set for the
command (see above), or the monitor's auto-input-scan is waking it. Fix the environment
variable first — it's the common one.

**Display is stale / showing yesterday.** Check the container is reachable from the display
device: open `http://YOUR-SERVER:8080/api/health` in its browser. The app refreshes data every
minute and reloads itself on new versions, so a stale screen almost always means a network
problem, not an app problem.

**Chromium shows "Restore pages?" after a power cut.** The
`--disable-session-crashed-bubble` flag in the autostart entry above suppresses it.

**Touches register in the wrong place.** The touchscreen needs mapping to the display. On
Wayland, set `output = HDMI-A-1` under the touch device in `~/.config/wayfire.ini`; on X11 use
`xinput map-to-output`.

**Everything is tiny on a 4K screen.** Set the Pi's desktop scaling to 200%, or add
`--force-device-scale-factor=2` to the Chromium flags, then set the app's text size to
`normal`.
