"""
The Unicorn HAT: 64 WS2812 LEDs in an 8×8 grid on GPIO 18, driven by rpi_ws281x (in ApplPi OS's image; it needs root
and the PWM hardware, hence "root" and "pwm" in app.json).

The light's frames are in reading order: index y * 8 + x, with (0, 0) the top left. With rotation 0 that's as seen
with the Pi's USB ports on the left (and its power and HDMI ports at the top); the rotation setting turns it to match
how the HAT is mounted. Here they're turned, gamma-corrected and held within the power limit before they're sent.

Without rpi_ws281x (on a PC), the frames are only kept, for the page's preview.
"""
from base.log import Log

TAG = 'HAT'
SIZE = 8
# Pimoroni's map from the grid to the LEDs' order along the chain (they zigzag), by [7 - x][y]: as checked on the HAT,
# with x read this way (0, 0) is the top left, seen from the front with the Pi's USB ports on the left
MAP = [
    [7, 6, 5, 4, 3, 2, 1, 0],
    [8, 9, 10, 11, 12, 13, 14, 15],
    [23, 22, 21, 20, 19, 18, 17, 16],
    [24, 25, 26, 27, 28, 29, 30, 31],
    [39, 38, 37, 36, 35, 34, 33, 32],
    [40, 41, 42, 43, 44, 45, 46, 47],
    [55, 54, 53, 52, 51, 50, 49, 48],
    [56, 57, 58, 59, 60, 61, 62, 63],
]
# A WS2812 draws about 20 mA per colour at full, and about 1 mA lit at all
MA_PER_CHANNEL = 20
MA_IDLE = 1
GAMMA = [int(255 * (i / 255) ** 2.2 + 0.5) for i in range(256)]
# Back from an LED's level to how bright it looks, for the page's preview (a screen applies its own gamma)
SEEN = [int(255 * (i / 255) ** (1 / 2.2) + 0.5) for i in range(256)]


def _rotated(x, y, rotation):
    if rotation == 90:
        return SIZE - 1 - y, x
    if rotation == 180:
        return SIZE - 1 - x, SIZE - 1 - y
    if rotation == 270:
        return y, SIZE - 1 - x
    return x, y


def drawn_ma(levels):
    """The current the LEDs draw for gamma-corrected levels (r, g, b, ...), in mA."""
    return sum(levels) * MA_PER_CHANNEL / 255 + MA_IDLE * len(levels) // 3


class UnicornHat:
    count = SIZE * SIZE

    def __init__(self, settings):
        self.settings = settings
        self.last = [(0, 0, 0)] * self.count  # what's showing, as it looks (after the limit), for the preview
        self.limited = False  # whether the last frame was dimmed to stay within the limit
        self.current_ma = 0  # what the last frame draws
        try:
            from rpi_ws281x import PixelStrip
        except ImportError:
            Log.warn(TAG, 'No rpi_ws281x (not on a Pi?): frames are only kept for the preview')
            self.strip = None
            return
        # 800 kHz, DMA channel 10, not inverted, full brightness (the app scales), PWM channel 0
        self.strip = PixelStrip(self.count, 18, 800000, 10, False, 255, 0)
        self.strip.begin()

    def show(self, frame):
        rotation = self.settings.get('device', 'rotation')
        limit = self.settings.get('device', 'max_current_ma')
        levels = [GAMMA[min(255, max(0, int(c + 0.5)))] for pixel in frame for c in pixel]
        ma = drawn_ma(levels)
        self.limited = ma > limit
        if self.limited:
            scale = (limit - MA_IDLE * self.count) / (ma - MA_IDLE * self.count)
            levels = [int(level * scale) for level in levels]
        self.current_ma = round(drawn_ma(levels))
        chain = [0] * self.count
        shown = [(0, 0, 0)] * self.count
        for i in range(self.count):
            r, g, b = levels[i * 3:i * 3 + 3]
            x, y = _rotated(i % SIZE, i // SIZE, rotation)
            chain[MAP[SIZE - 1 - x][y]] = (r << 16) | (g << 8) | b
            shown[i] = (SEEN[r], SEEN[g], SEEN[b])
        self.last = shown
        if self.strip is not None:
            for index, colour in enumerate(chain):
                self.strip.setPixelColor(index, colour)
            self.strip.show()
