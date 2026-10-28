# Roadmap

ApplPi Unicorn is an ApplPi OS app for the original Pimoroni Unicorn HAT: 64 WS2812 LEDs in an 8×8 grid on GPIO 18.
It's a light, controlled like PlasmaStick Controller (the web page, the JSON API, MQTT and Home Assistant), with
modes from the 2015-2022 `uhcontrol.py` script it replaces, which took `{"opcode": ...}` commands over MQTT (nothing
sends those any more, so they aren't kept).

## Design

- **ApplPi OS app**, one per Pi: `/data/app`, `app.json` with `"root": true` (`rpi_ws281x` needs `/dev/mem`) and
  `"pwm": true` (ApplPi OS unloads the onboard audio's driver while it runs, as both use the PWM hardware), its
  settings in `/data/app-state`, deployed with `deploy.ps1`. `rpi_ws281x` is in the image (v0.4).
- **Built on App Base** (its first user): the web server, settings, MQTT, Home Assistant discovery and the light
  model, vendored in `src/base/`.
- **The LEDs**: Pimoroni's `unicornhat` library isn't needed; the app drives the 64 pixels through `rpi_ws281x`
  itself (the grid is a zigzag, which the app maps), with a rotation setting (0, 90, 180, 270) for how the HAT is
  mounted.
- **A brightness limit**: all 64 at full white draw about 3.5 A, more than a Pi 2 can supply. The app scales
  everything so the most it can draw is within the Pi's supply (a setting, with a hard ceiling); 100% brightness
  means that limit. Pimoroni's own advice was to stay below half.

### Modes

As PlasmaStick's, with `Mode` and `ModeParameters`:

| Mode | From | Shows |
|---|---|---|
| Colour | opcodes 1-4 | The whole panel one colour, or a white by temperature (`Kelvin`) |
| Rainbows | new | Rainbow colours moving across the grid |
| Pulse | opcode 40 | A glow growing and shrinking from the centre, in a colour (purple by default) |
| F1 Start | opcode 50 | As F1 starts since 2026: the panels flash blue for 5 s (pre-start), the five red lights come on a second apart, and after a random 0.2-3 s they go out; then off. (The 2015 script lit four pairs of columns and waited 4-7 s.) |
| Pirate Flag | opcode 10 | The skull and crossbones, filling with red row by row, over and over |
| CPU Chart | opcode 60 | An 8-column history of another device's CPU use (green, orange, red), from a field of its MQTT topic (the `chart` settings) |
| Status | new | This Pi's temperature and load, and alerts other devices post to it (step 5) |

Animations take a `Speed` (1-10), as PlasmaStick's do. Home Assistant sees a light with RGB colour, colour
temperature, brightness and the modes as effects.

### Alerts

Asked for on 2026-10-27, for events such as a motion sensor by the door (a doggy doorbell): with the Alerts switch
on, an alert interrupts whatever the light is doing, on or off, flashing a colour (this long on, this long off) for
a while at its own brightness, and then the light carries on as it was. The colour, times and brightness are
settings, and each alert can give its own. Alerts come from the API (`/api/alert`), MQTT (`<base>/alert`), Home
Assistant (an Alert button, and the Alerts switch), or a watched topic: another device's, such as Pico PIR's state
topic, where motion starting rings once until it clears. The page has a Test button, which works with the switch
off. This is App Base's (the light model), so PlasmaStick gets it too.

### Schedule and groups

Both come from App Base. The schedule turns the light on or off, into a mode or to a brightness at set times or at
sunrise and sunset (needing the Pi's location). In a group, it follows the other lights in it, PlasmaStick ones
included: power and brightness always, and the mode when it has it (it has no Fire, Ocean or Christmas, so it
keeps its own then; PlasmaStick likewise ignores the Unicorn's own modes).

### Not in the first version

CheerLights, which PlasmaStick has, could come later.

## Steps

### 1. Lights on

Colour mode, brightness, rotation and the limit, on the web page (Control and Device tabs) and the JSON API
(`/api/info`, `/api/power/*`, `/api/mode`, `/api/brightness`, `/api/config`), with App Base's portable layer.
Checked on the HAT.

### 2. MQTT and Home Assistant

The topics, messages and discovery as PlasmaStick's, with an MQTT tab.

### 3. The modes

Rainbows, Pulse, F1 Start, Pirate Flag and CPU Chart, and alerts. Checked on the HAT.

### 4. Schedule and groups

A Schedule tab, and the group setting on the MQTT tab, from App Base. Checked with a PlasmaStick in the same group.
The page matches PlasmaStick's (its tabs, power switch, mode buttons and colour row, from App Base), with the
preview above the controls and an Alert tab. The schedule uses the Pi's clock, whose time zone and time server
are set on the Schedule tab (ApplPi OS v0.4's app requests).

### 5. Finish

README, tests, the first release, and a Pi running it.
v0.1.0 (2026-10-27), on App Base v0.1.0. v0.2.0 (2026-10-27), on App Base v0.2.0: deploys over Wi-Fi, the
Pi's clock and restarting the Pi from the page, and systemd's watchdog. It needs ApplPi OS v0.4 (`rpi_ws281x`,
`"pwm"` and the app requests). v0.3.0 (2026-10-28), on App Base v0.3.0: the Pi's name, the Wi-Fi fallback
and a factory reset on the Device tab, with ApplPi OS v0.5's setup mode. The repos stay private until the app contract is settled, near ApplPi OS v1.

### 6. Status and alerts

This Pi's temperature and load as a mode, and alerts with more than a colour (an icon or a scrolling word).
