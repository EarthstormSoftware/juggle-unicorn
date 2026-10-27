"""
The platform for an ApplPi OS app: what the OS does that a Pico does itself.

The app's state (config.json and anything else it writes) is in APPLPI_STATE (/data/app-state), as the rest of the Pi
is read-only. The device name is the Pi's: it's shown, not changed (SSH and applpi know the Pi by it). A restart ends
the app, which systemd starts again.
"""
import os
import socket
import subprocess
import time
from pathlib import Path

NAME_EDITABLE = False
STATE = os.environ.get('APPLPI_STATE', str(Path.cwd() / 'state'))
# 80 on the Pi; PORT for trying it on a PC where 80 is taken
PORT = int(os.environ.get('PORT', 80))
_STARTED = time.monotonic()


def state_path(name):
    os.makedirs(STATE, exist_ok=True)
    return os.path.join(STATE, name)


def device_name():
    return socket.gethostname()


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except OSError:
        return None


def health():
    """The Pi's health for /api/info."""
    temperature = _read('/sys/class/thermal/thermal_zone0/temp')
    uptime = _read('/proc/uptime')
    release = dict(line.split('=', 1) for line in (_read('/etc/applpi-release') or '').splitlines() if '=' in line)
    try:
        slot = subprocess.run(['/usr/lib/applpi/slot'], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        slot = None
    now, _ = local_time()
    return {
        # Local time, as a Pico gives it: YYYY-MM-DDTHH:MM:SS, or None until the clock is right
        'time': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime()) if now is not None else None,
        'time_zone': time_zone(),
        'app_uptime_s': int(time.monotonic() - _STARTED),
        'uptime_s': int(float(uptime.split()[0])) if uptime else None,
        'temperature_c': round(int(temperature) / 1000, 1) if temperature else None,
        'load': round(os.getloadavg()[0], 2) if hasattr(os, 'getloadavg') else None,
        'os': {'version': release.get('VERSION'), 'build': release.get('BUILD_STAMP'), 'slot': slot or None},
    }


# systemd-timesyncd makes this once the clock is right (a Pi has no clock of its own while it's off)
SYNCHRONIZED = '/run/systemd/timesync/synchronized'


def local_time():
    """(local seconds since 1970, local time minus UTC in seconds), or (None, None) until the clock is right. Off a
    Pi (no timesyncd), the clock is taken as right."""
    if os.path.isdir('/run/systemd') and not os.path.exists(SYNCHRONIZED):
        return None, None
    now = time.time()
    offset = time.localtime(now).tm_gmtoff
    return int(now) + offset, offset


def time_zone():
    """The Pi's time zone's name (set when the card is flashed), such as Europe/London."""
    try:
        target = os.path.realpath('/etc/localtime')
    except OSError:
        return None
    return target.split('zoneinfo/', 1)[1] if 'zoneinfo/' in target else None


def mqtt_client(**options):
    from base.mqttclient import Client
    return Client(**options)


def restart():
    """Ends the app; systemd starts it again (Restart=always)."""
    os._exit(0)
