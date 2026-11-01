"""
The Unicorn's modes beyond Colour, as App Base effects: each is made with (count, parameters, light) and gives
frame(now) -> 64 (r, g, b) in reading order ((0, 0) top left), at full brightness; the light scales them.

Rainbows, Pulse and Pirate Flag take a Speed (1-10; without one, the light's Animation Speed setting); Pulse also a
Colour.
"""
import math
import random

from base.light import rgb

SIZE = 8
OFF = (0, 0, 0)


def _hsv(h, s, v):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return r * 255, g * 255, b * 255


class Rainbows:
    """Rainbow colours moving diagonally across the grid."""

    def __init__(self, count, parameters, light):
        self.parameters = parameters
        self.light = light
        self.start = None

    def frame(self, now):
        if self.start is None:
            self.start = now
        # Speed 5: once through the colours every 4 s
        turn = (now - self.start) / 1000 * 0.05 * self.light.speed()
        return [_hsv(((x + y) / 28 + turn) % 1, 1, 1) for y in range(SIZE) for x in range(SIZE)]


class Pulse:
    """A glow growing from the centre and shrinking back, in a colour (purple by default)."""
    COLOUR = '#d633ff'

    def __init__(self, count, parameters, light):
        self.parameters = parameters
        self.light = light
        self.start = None

    def frame(self, now):
        if self.start is None:
            self.start = now
        colour = rgb(self.parameters.get('colour') or self.COLOUR)
        # Speed 5: a pulse every 0.8 s; the glow's width (at half strength) between 0.6 and 5 LEDs
        period = 4000 / self.light.speed()
        phase = ((now - self.start) % period) / period
        width = 0.6 + 4.4 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
        spread = -4 * math.log(2) / (width * width)
        pixels = []
        for y in range(SIZE):
            for x in range(SIZE):
                v = math.exp(spread * ((x - 3.5) ** 2 + (y - 3.5) ** 2))
                pixels.append(tuple(c * v for c in colour))
        return pixels


class F1Start:
    """A Formula 1 start, as since 2026: the panels flash blue for 5 s (pre-start), then the five red lights come on a
    second apart, and after a random 0.2-3 s they all go out, and so does the light. Five panels, one column each, with
    their lights in pairs."""
    BLUE = (0, 80, 255)
    RED = (255, 0, 0)
    COLUMNS = (1, 2, 3, 4, 5)
    ROWS = (1, 2, 5, 6)
    PRE_START_MS = 5000
    LIGHT_MS = 1000

    def __init__(self, count, parameters, light):
        self.start = None
        self.out_at = self.PRE_START_MS + self.LIGHT_MS * len(self.COLUMNS) + random.randint(200, 3000)
        self.finished = False

    def frame(self, now):
        if self.start is None:
            self.start = now
        t = now - self.start
        lit = {}
        if t < self.PRE_START_MS:
            if t % 1000 < 500:
                lit = {column: self.BLUE for column in self.COLUMNS}
        elif t < self.out_at:
            reds = min(len(self.COLUMNS), (t - self.PRE_START_MS) // self.LIGHT_MS)
            lit = {column: self.RED for column in self.COLUMNS[:reds]}
        else:
            self.finished = True
        return [lit.get(x, OFF) if y in self.ROWS else OFF for y in range(SIZE) for x in range(SIZE)]


# The skull and crossbones, and the order it fills with red (from the 2015 script)
_FLAG_STEPS = (
    ((2, 0), (3, 0), (4, 0), (5, 0), (6, 0)),
    ((4, 1),),
    ((4, 2), (6, 1)),
    ((6, 2), (2, 1)),
    ((4, 4), (2, 2)),
    ((3, 2), (5, 2)),
    ((6, 5), (4, 6), (3, 3), (5, 3)),
    ((2, 5),),
    ((6, 7),),
    ((2, 7), (3, 6), (5, 6)),
)
_FLAG = set(p for step in _FLAG_STEPS for p in step)


class PirateFlag:
    """The skull and crossbones in white, filling with red step by step, over and over."""
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    HOLD_MS = 2000

    def __init__(self, count, parameters, light):
        self.parameters = parameters
        self.light = light
        self.start = None

    def frame(self, now):
        if self.start is None:
            self.start = now
        step_ms = 1000 / self.light.speed()  # speed 5: 0.2 s a step
        cycle = 2 * self.HOLD_MS + step_ms * len(_FLAG_STEPS)
        t = (now - self.start) % cycle
        steps = 0 if t < self.HOLD_MS else min(len(_FLAG_STEPS), int((t - self.HOLD_MS) // step_ms) + 1)
        red = set(p for step in _FLAG_STEPS[:steps] for p in step)
        return [self.RED if (x, y) in red else self.WHITE if (x, y) in _FLAG else OFF
                for y in range(SIZE) for x in range(SIZE)]


# The last 8 readings for CPU Chart, newest first (product.py keeps them from the chart topic)
readings = []

_GREEN, _ORANGE, _BAR_RED = (0, 255, 0), (255, 153, 0), (255, 0, 0)


class CpuChart:
    """A history of another device's CPU use (from its MQTT topic): one column a reading, newest on the left, each a
    bar from the bottom in eighths, green, then orange above 5/8 and red above 7/8."""

    def __init__(self, count, parameters, light):
        pass

    def frame(self, now):
        pixels = [OFF] * (SIZE * SIZE)
        for x, percent in enumerate(readings[:SIZE]):
            for level in range(SIZE):
                if level and percent <= level * 12.5:
                    break
                colour = _GREEN if level < 5 else _ORANGE if level < 7 else _BAR_RED
                pixels[(SIZE - 1 - level) * SIZE + x] = colour
        return pixels


MODES = {
    'Rainbows': Rainbows,
    'Pulse': Pulse,
    'F1 Start': F1Start,
    'Pirate Flag': PirateFlag,
    'CPU Chart': CpuChart,
}
