"""ApplPi Unicorn: the Pimoroni Unicorn HAT as a light, on App Base. See docs/roadmap.md."""
import json
from pathlib import Path

from base.settings import Setting, is_int, is_one_of
from hat import UnicornHat

NAME = 'Unicorn'
VERSION = json.loads((Path(__file__).parent / 'app.json').read_text(encoding='utf-8'))['version']

# The modes beyond Colour (step 3)
LIGHT_MODES = {}

SETTINGS = {
    'device': {
        'default_mode': Setting('Colour', is_one_of('Colour', *LIGHT_MODES)),
        # How the HAT is mounted: the grid is turned by this many degrees
        'rotation': Setting(0, is_one_of(0, 90, 180, 270)),
        # All 64 at full white draw about 3.8 A, more than a Pi 2's supply can give: frames that would draw more are
        # dimmed to this. 2 A at most, which leaves a 3 A supply room for the Pi.
        'max_current_ma': Setting(1200, is_int(300, 2000)),
    },
}


def output(device):
    return UnicornHat(device.settings)


def info(device):
    hat = device.light.output
    return {'hat': {'connected': hat.strip is not None, 'limited': hat.limited, 'current_ma': hat.current_ma}}


def routes(app, device):
    @app.get('/api/pixels')
    async def pixels(request):
        """What the HAT shows, for the page's preview: 64 '#rrggbb', in reading order."""
        return {'pixels': ['#{:02x}{:02x}{:02x}'.format(*p) for p in device.light.output.last]}
