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
    return {
        'app_uptime_s': int(time.monotonic() - _STARTED),
        'uptime_s': int(float(uptime.split()[0])) if uptime else None,
        'temperature_c': round(int(temperature) / 1000, 1) if temperature else None,
        'load': round(os.getloadavg()[0], 2) if hasattr(os, 'getloadavg') else None,
        'os': {'version': release.get('VERSION'), 'build': release.get('BUILD_STAMP'), 'slot': slot or None},
    }


def mqtt_client(**options):
    from base.mqttclient import Client
    return Client(**options)


def restart():
    """Ends the app; systemd starts it again (Restart=always)."""
    os._exit(0)
