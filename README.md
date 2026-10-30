# Juggle Unicorn

The original [Pimoroni Unicorn HAT](https://shop.pimoroni.com/products/unicorn-hat) (64 RGB LEDs in an 8×8 grid) as
a light, on a Raspberry Pi running [Juggle OS](https://github.com/EarthstormSoftware/juggle-os). It's controlled
like PlasmaStick Controller: the same web page, JSON API, MQTT topics and Home Assistant light, and it joins
PlasmaStick groups.

- **Modes**: Colour (or a white by temperature), Rainbows, Pulse, F1 Start (as Formula 1 starts since 2026: five
  seconds of blue, the five reds a second apart, then lights out), Pirate Flag and CPU Chart (another device's CPU
  use, from its MQTT topic).
- **Alerts**: with alerts switched on, an alert interrupts the light, on or off, flashing a colour for a while, then
  it carries on as it was. From a watched MQTT topic (a motion sensor by the door, say), Home Assistant, MQTT or
  the API.
- **Schedule**: up to 8 events, at a time or at sunrise or sunset, on chosen days.
- **Groups**: lights with the same group name follow each other, PlasmaSticks included.
- **A preview** of the HAT on the page, and a **power limit**: 64 LEDs at full white would draw about 3.8 A, so
  anything over the limit (1200 mA unless set otherwise) is dimmed to it.

It's built on [App Base](https://github.com/EarthstormSoftware/app-base), the code the Earthstorm devices share,
kept as a copy in `app/base/`.

## What it needs

- A Raspberry Pi with a 40-pin header (developed on a Pi 2) and the original Unicorn HAT (not the HD or Mini).
- **Juggle OS from the release after v0.6.0**: the first that knows `juggle` in `app.json` (Juggle 1.0, the app
  contract). The library it needs, `rpi_ws281x`, and `"pwm": true` in `app.json`, with which the OS turns off the
  onboard audio while the app runs (both use the PWM hardware), came in v0.4.

## Deploying it

On Windows, with the Pi set up by `juggle flash` (so SSH works with your key):

```powershell
.\deploy.ps1 [name]
```

The name defaults to `jugglepi`. It copies the app to the Pi, which replaces the app it had, starts this one and says
whether it's running. Then it's at `http://<name>.local`. Its settings are kept through deploys and OS updates.

Once it's running, a new version can also go over Wi-Fi, to the app itself, with no SSH key:

```powershell
.\deploy.ps1 [name] -WiFi [-Password <the web password>]
```

The Pi tries the new version and goes back to the old one if it doesn't keep running.

## The page

| Tab | Has |
|---|---|
| Control | The preview, power, brightness, the modes, speed, colour and white |
| Device | The HAT's rotation and power limit, what it does at power-up, CPU Chart's topic, the web password, the log level, restart, restarting the Pi and reset; on Juggle OS v0.5 or later, the Pi's name, the Wi-Fi fallback and a factory reset |
| MQTT | The broker, the topic base, the group, and Home Assistant discovery |
| Schedule | The location (for sunrise and sunset), the events, and the Pi's clock: its time zone and time server |
| Alert | The Alerts switch, Test and Stop, the alert's colour, timing and brightness, and the topic to watch |

## The API

As PlasmaStick's, from App Base:

| Request | Does |
|---|---|
| `GET /api/info` | The light, the HAT (`connected`, `limited`, `current_ma`), MQTT, the Pi and the OS |
| `POST /api/power/on`, `/off`, `/toggle` | Turns the light on or off |
| `POST /api/mode` | `{"mode": "Pulse", "parameters": {"Colour": "#00ff80", "Speed": 7}}` |
| `POST /api/brightness` | `{"brightness": 40}` (1-100) |
| `POST /api/alert` | Starts an alert, if alerts are on: `{}`, or any of `colour`, `seconds`, `on_ms`, `off_ms`, `brightness`; `"test": true` shows one with alerts off |
| `POST /api/alert/stop` | Ends one |
| `GET /api/pixels` | What the HAT shows: 64 `#rrggbb` in reading order |
| `GET`, `POST /api/config` | The settings |
| `POST /api/restart`, `/api/reset` | Restarts the app; resets the settings (`{"confirm": true}`) |
| `GET`, `POST /api/clock` | The Pi's time zone and time server |
| `GET`, `POST /api/update` | How the last update went; a new version of the app, as a tar (what `deploy.ps1 -WiFi` sends) |
| `POST /api/reboot` | Restarts the Pi |
| `GET`, `POST /api/wifi` | The Wi-Fi fallback: setup mode when Wi-Fi doesn't connect (Juggle OS v0.5) |
| `POST /api/setup-mode`, `/api/factory-reset` | Restarts the Pi in setup mode, to rename it; forgets the Pi's settings and starts setup mode (both `{"confirm": true}`) |

POSTs from other sites' pages are refused, and with a web password set every request needs it.

## MQTT

Under the topic base (`/home/device/{name}` unless changed):

| Topic | Is |
|---|---|
| `<base>/control` | Commands, as PlasmaStick's: `{"MessageType": "StateChange", "Parameters": {"State": true}}`, `ModeChange` (`Mode`, `ModeParameters`) and `BrightnessChange` (`Brightness`) |
| `<base>/state` | The state, retained: `{"State", "Mode", "ModeParameters", "Brightness"}` |
| `<base>/alert` | Starts an alert (empty, or `{"Colour", "Seconds", "OnMs", "OffMs", "Brightness"}`); `{"Active": false}` ends one |
| `<base>/alert/set`, `<base>/alert/state` | `{"Enabled": true}` switches alerts on; their state, retained |
| `<base>/status`, `<base>/info` | `online` or `offline`, and the Pi's health every minute, retained |
| `<base>/ha/state`, `<base>/ha/set` | Home Assistant's JSON light schema |
| `earthstorm/group/<group>` | The group's state, and `plasmastick/group/<group>` until PlasmaStick is on App Base |

With discovery on, Home Assistant finds the light (with the modes as effects), an Alert button, an Alerts switch and
the Pi's uptime, temperature, load and free memory.

## Developing

`py -m pytest` runs the tests (Python 3.11 or later; no Pi needed). The app runs on a PC too, without the HAT, which
the preview stands in for:

```powershell
$env:PORT = 8080; py app\main.py
```

Its settings are then in `app\state\`.

`app\base\` is a copy of App Base, which the tests check is unchanged: a fix goes into App Base, then
`..\app-base\update-base.ps1 -Product app` copies it in (`-Tag vX.Y.Z` for a release of App Base).

To release: copy in a tagged App Base, put the version in `app\app.json`, check on the HAT, and tag `vX.Y.Z`.

## Licence

MIT. See [LICENSE](LICENSE). Microdot is MIT too: see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
