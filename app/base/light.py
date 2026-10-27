"""
The light model, for products that are lights (PlasmaStick, the Unicorn HAT): on or off, a mode with its parameters,
a brightness (1-100%), and fades between them. The product gives its modes beyond Colour (MODES: name to an effect
class) and its LEDs (an output with count and show(frame)); the light draws frames and hands them over.

A frame is a list of (r, g, b), 0-255, one per LED, already scaled for brightness and fades. The output does what's
particular to its LEDs: gamma, the order of the pixels, a power limit.

Effects are classes made with (count, parameters, product) that give frame(ms) -> the next frame at full brightness,
and their Speed (1-10) in parameters if they take one. (Effects come in a later step.)
"""
from base.compat import asyncio, ticks_ms, ticks_diff, sleep_ms
from base.log import Log
from base.settings import Setting, is_int, is_bool

TAG = 'LIGHT'

MIN_KELVIN, MAX_KELVIN = 2000, 6500
DEFAULT_COLOUR = '#ffb46b'  # a warm white
# A frame every 20 ms while something moves (a fade or an animation)
FRAME_MS = 20
_HEX_DIGITS = '0123456789abcdefABCDEF'


def is_valid_colour(value):
    """True for a '#RRGGBB' (or 'RRGGBB') hex colour string."""
    if not isinstance(value, str):
        return False
    digits = value[1:] if value.startswith('#') else value
    return len(digits) == 6 and all(c in _HEX_DIGITS for c in digits)


def rgb(colour):
    digits = colour[1:] if colour.startswith('#') else colour
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def hex_colour(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))


def is_valid_kelvin(value):
    return isinstance(value, int) and not isinstance(value, bool) and MIN_KELVIN <= value <= MAX_KELVIN


def kelvin_colour(kelvin):
    """The '#rrggbb' of white light at kelvin (the usual fit to the black-body curve)."""
    from math import log
    t = kelvin / 100
    if t <= 66:
        r, g = 255, 99.4708025861 * log(t) - 161.1195681661
    else:
        r, g = 329.698727446 * (t - 60) ** -0.1332047592, 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * log(t - 10) - 305.0447927307
    return '#{:02x}{:02x}{:02x}'.format(*(min(255, max(0, int(v + 0.5))) for v in (r, g, b)))


def _is_colour(value):
    return None if is_valid_colour(value) else 'must be a #RRGGBB hex colour'


# The settings every light has, next to BASE_SETTINGS (the product adds the default mode's choices)
LIGHT_SETTINGS = {
    'device': {
        'default_state': Setting(True, is_bool),
        'default_mode': Setting('Colour'),
        'default_colour': Setting(DEFAULT_COLOUR, _is_colour),
        'default_brightness': Setting(66, is_int(1, 100)),
        # Turning on and off, and changing the brightness or colour, fade over this long (0: at once)
        'transition_ms': Setting(500, is_int(0, 10000)),
    },
}


class Light:
    def __init__(self, output, settings, modes=None, product=None, min_level=0.06):
        """output: the LEDs (count, show(frame)); modes: the product's effects by name; min_level: the share of full
        output that 1% brightness draws (the dimmest a full channel still shows on these LEDs)."""
        self.output = output
        self.settings = settings
        self.effects = modes or {}
        self.modes = ('Colour',) + tuple(self.effects)
        self.product = product
        self.min_level = min_level
        self.on = False
        self.mode = 'Colour'
        self.parameters = {'Colour': settings.get('device', 'default_colour')}
        self.brightness = settings.get('device', 'default_brightness')
        # Told of every change (MQTT state, groups): listener(light)
        self.listeners = []
        self._effect = None
        # What's drawn: the level (0-1, brightness and fades) and, in Colour mode, the colour, each fading to its target
        self._level = 0.0
        self._level_fade = None  # (from, to, start, ms)
        self._colour = rgb(self.parameters['Colour'])
        self._colour_fade = None  # (from rgb, to rgb, start, ms)
        self._wake = asyncio.Event()
        default_mode = settings.get('device', 'default_mode')
        error = self.set(on=settings.get('device', 'default_state'),
                         mode=default_mode if default_mode in self.modes else 'Colour', transition_ms=0)
        if error:
            Log.warn(TAG, 'Default mode: ' + error)

    # Changes

    def parameters_error(self, mode, parameters):
        """Why parameters can't be used for mode, or None if they can."""
        if mode not in self.modes:
            return 'Mode must be one of ' + ', '.join(self.modes)
        if parameters is None:
            return None
        if not isinstance(parameters, dict):
            return 'Mode parameters must be an object'
        if mode == 'Colour':
            if 'Colour' in parameters and not is_valid_colour(parameters['Colour']):
                return 'Colour must be a #RRGGBB hex colour'
            if 'Kelvin' in parameters and not is_valid_kelvin(parameters['Kelvin']):
                return 'Kelvin must be a whole number, {}-{}'.format(MIN_KELVIN, MAX_KELVIN)
        elif 'Speed' in parameters and (not isinstance(parameters['Speed'], int) or not 1 <= parameters['Speed'] <= 10):
            return 'Speed must be a whole number, 1-10'
        return None

    def set(self, on=None, mode=None, parameters=None, brightness=None, transition_ms=None):
        """Changes what the light does; anything None stays as it is. Returns why it couldn't, or None."""
        if mode is not None or parameters is not None:
            new_mode = self.mode if mode is None else mode
            error = self.parameters_error(new_mode, parameters)
            if error:
                return error
        if brightness is not None and (not isinstance(brightness, int) or isinstance(brightness, bool)
                                       or not 1 <= brightness <= 100):
            return 'Brightness must be a whole number, 1-100'
        fade = self.settings.get('device', 'transition_ms') if transition_ms is None else transition_ms
        before = self.state()

        if mode is not None and mode != self.mode:
            self.mode = mode
            # A new mode starts from its defaults; Colour keeps its colour
            self.parameters = {'Colour': hex_colour(*self._colour)} if mode == 'Colour' else {}
            self._effect = None
        if parameters:
            if self.mode == 'Colour' and 'Kelvin' in parameters:
                parameters = dict(parameters, Colour=kelvin_colour(parameters['Kelvin']))
            elif self.mode == 'Colour' and 'Colour' in parameters:
                self.parameters.pop('Kelvin', None)
            self.parameters.update(parameters)
            if self._effect is not None and hasattr(self._effect, 'update'):
                self._effect.update(self.parameters)
        if self.mode == 'Colour':
            self._fade_colour(rgb(self.parameters['Colour']), fade)
        if brightness is not None:
            self.brightness = brightness
        if on is not None:
            self.on = on
        self._fade_level(self._target_level(), fade)

        if self.state() != before:
            Log.info(TAG, 'Now {}'.format(self.state()))
            for listener in self.listeners:
                listener(self)
        self._wake.set()
        return None

    def toggle(self):
        self.set(on=not self.on)
        return self.on

    def state(self):
        """As PlasmaStick's MQTT state: {"State", "Mode", "ModeParameters", "Brightness"}."""
        return {'State': self.on, 'Mode': self.mode, 'ModeParameters': dict(self.parameters),
                'Brightness': self.brightness}

    # Drawing

    def _target_level(self):
        if not self.on:
            return 0.0
        return self.min_level + (1 - self.min_level) * (self.brightness - 1) / 99

    def _fade_level(self, target, ms):
        self._level_fade = (self._level, target, ticks_ms(), ms) if ms > 0 else None
        if ms <= 0:
            self._level = target

    def _fade_colour(self, target, ms):
        # Only while it's showing: switched off, the colour just changes
        if ms > 0 and self._level > 0 and target != self._colour:
            self._colour_fade = (self._colour, target, ticks_ms(), ms)
        else:
            self._colour, self._colour_fade = target, None

    def _step(self, now):
        """Moves the fades on; True while anything is still moving."""
        moving = False
        if self._level_fade:
            start_level, end_level, start, ms = self._level_fade
            done = min(1, ticks_diff(now, start) / ms)
            self._level = start_level + (end_level - start_level) * done
            self._level_fade = None if done >= 1 else self._level_fade
            moving = moving or done < 1
        if self._colour_fade:
            start_rgb, end_rgb, start, ms = self._colour_fade
            done = min(1, ticks_diff(now, start) / ms)
            self._colour = tuple(a + (b - a) * done for a, b in zip(start_rgb, end_rgb))
            self._colour_fade = None if done >= 1 else self._colour_fade
            moving = moving or done < 1
        return moving

    def frame(self, now):
        """The frame to show now, and whether the light is moving (another frame is due soon)."""
        moving = self._step(now)
        level = self._level
        if level <= 0:
            return [(0, 0, 0)] * self.output.count, moving
        if self.mode == 'Colour':
            pixel = tuple(c * level for c in self._colour)
            return [pixel] * self.output.count, moving
        if self._effect is None:
            self._effect = self.effects[self.mode](self.output.count, self.parameters, self.product)
        return [tuple(c * level for c in p) for p in self._effect.frame(now)], True

    async def run(self):
        """Draws while anything moves, and waits for a change otherwise."""
        last = None
        while True:
            pixels, moving = self.frame(ticks_ms())
            if pixels != last:
                try:
                    self.output.show(pixels)
                except Exception as e:
                    Log.error(TAG, 'Showing a frame: {}'.format(e))
                last = pixels
            if moving:
                await sleep_ms(FRAME_MS)
            else:
                self._wake.clear()
                await self._wake.wait()
