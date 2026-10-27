"""ApplPi Unicorn: the Pimoroni Unicorn HAT as a light, on App Base. See docs/roadmap.md."""
import json
from pathlib import Path

from base.log import Log
from base.mqtt import watch_topic_error
from base.settings import Setting, is_int, is_one_of, is_text
import effects
from hat import UnicornHat

NAME = 'Unicorn'
VERSION = json.loads((Path(__file__).parent / 'app.json').read_text(encoding='utf-8'))['version']
# For Home Assistant
MANUFACTURER = 'Pimoroni'
MODEL = 'Unicorn HAT'
TAG = 'UNICORN'

LIGHT_MODES = effects.MODES

SETTINGS = {
    'device': {
        'default_mode': Setting('Colour', is_one_of('Colour', *LIGHT_MODES)),
        # How the HAT is mounted: the grid is turned by this many degrees
        'rotation': Setting(0, is_one_of(0, 90, 180, 270)),
        # All 64 at full white draw about 3.8 A, more than a Pi 2's supply can give: frames that would draw more are
        # dimmed to this. 2 A at most, which leaves a 3 A supply room for the Pi.
        'max_current_ma': Setting(1200, is_int(300, 2000)),
    },
    # CPU Chart: another device's MQTT topic, the field in its JSON with the reading (or the whole message, if it's
    # a number), and the reading that fills a column
    'chart': {
        'topic': Setting('', watch_topic_error, restart=True),
        'field': Setting('cpu_usage', is_text(40)),
        'full_scale': Setting(100, is_int(1, 1000000)),
    },
}


def output(device):
    return UnicornHat(device.settings)


def info(device):
    hat = device.light.output
    return {'hat': {'connected': hat.strip is not None, 'limited': hat.limited, 'current_ma': hat.current_ma}}


def mqtt_topics(device):
    topic = device.settings.get('chart', 'topic')
    return [topic] if topic else []


def mqtt_message(device, topic, text):
    """A reading for CPU Chart, kept whatever the mode, so the chart has a history when it's chosen."""
    field = device.settings.get('chart', 'field')
    try:
        payload = json.loads(text)
        value = payload[field] if isinstance(payload, dict) else payload
        value = float(value)
    except (ValueError, KeyError, TypeError):
        Log.debug(TAG, 'No {} in the chart topic: {}'.format(field, text[:80]))
        return
    percent = max(0.0, min(100.0, value * 100 / device.settings.get('chart', 'full_scale')))
    effects.readings.insert(0, percent)
    del effects.readings[8:]


def routes(app, device):
    @app.get('/api/pixels')
    async def pixels(request):
        """What the HAT shows, for the page's preview: 64 '#rrggbb', in reading order, and whether it's moving (an
        alert, or an animation), so the page checks more often."""
        light = device.light
        moving = 'alert' if light.alerting else 'mode' if light.on and light.mode not in STILL else 'none'
        return {'pixels': ['#{:02x}{:02x}{:02x}'.format(*p) for p in light.output.last], 'moving': moving}


# Modes that only change now and then
STILL = ('Colour', 'CPU Chart')
