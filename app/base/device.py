"""
The device: a product, the platform it runs on, its settings, its light (if it's one) and its web server.

A product is a module (product.py) with:
  NAME, VERSION                 what the page and /api/info show
  MANUFACTURER, MODEL           optional: the hardware, for Home Assistant (default: Earthstorm Software, NAME)
  SETTINGS                      its own settings ({section: {key: Setting}}), next to the base's
  LIGHT_MODES (lights only)     its effects by name ({} for Colour only); with it, the product is a light
  output(device) (lights only)  its LEDs: an object with count and show(frame)
  info(device)                  optional: its own fields for /api/info
  routes(app, device)           optional: its own API routes
  applied(device, changed)      optional: settings changed ((section, key) pairs) that apply at once
  tasks(device)                 optional: coroutines to run alongside
  www                           optional: the folder with its index.html (default: www beside product.py)

main.py starts it: run(product).
"""
from base.compat import MICROPYTHON, asyncio, mem_free, collect, beside
from base.log import Log
from base.settings import Settings, BASE_SETTINGS, merge

TAG = 'DEVICE'
PORT = 80


class Device:
    def __init__(self, product, platform):
        self.product = product
        self.platform = platform
        is_light = hasattr(product, 'LIGHT_MODES')
        from base.mqtt import MQTT_SETTINGS
        schemas = [BASE_SETTINGS, MQTT_SETTINGS, product.SETTINGS]
        if is_light:
            from base.light import LIGHT_SETTINGS
            from base.schedule import schedule_settings
            schemas[1:1] = [LIGHT_SETTINGS, schedule_settings(('Colour',) + tuple(product.LIGHT_MODES))]
        self.settings = Settings(platform.state_path('config.json'), merge(*schemas))
        Log.level = self.settings.get('device', 'log_level')
        self.www = getattr(product, 'www', None) or beside(product.__file__, 'www')
        self.light = None
        if is_light:
            from base.light import Light
            self.light = Light(product.output(self), self.settings, product.LIGHT_MODES, product)
        self.mqtt = None  # until it's made, as making it asks info() which figures there are
        from base.mqtt import Mqtt
        self.mqtt = Mqtt(self)

    def info(self):
        collect()
        info = {
            'product': self.product.NAME,
            'version': self.product.VERSION,
            'name': self.platform.device_name(),
            'name_editable': self.platform.NAME_EDITABLE,
            'mem_free': mem_free(),
        }
        info.update(self.platform.health())
        if self.light is not None:
            light = self.light
            info['light'] = {
                'state': light.on,
                'mode': light.mode,
                'parameters': light.parameters,
                'brightness': light.brightness,
                'modes': light.modes,
                'alert': {'enabled': self.settings.get('alert', 'enabled'), 'active': light.alerting},
            }
        if self.mqtt is not None:
            info['mqtt'] = self.mqtt.status()
        if hasattr(self.product, 'info'):
            info.update(self.product.info(self))
        return info

    def applied(self, changed):
        """Settings that changed and apply at once (the rest wait for the restart)."""
        if ('device', 'log_level') in changed:
            Log.level = self.settings.get('device', 'log_level')
        if ('alert', 'enabled') in changed:
            # Switching alerts off silences one that's showing
            if not self.settings.get('alert', 'enabled'):
                self.light.stop_alert()
            self.mqtt.alert_switched()
        if hasattr(self.product, 'applied'):
            self.product.applied(self, changed)

    def reset(self):
        Log.warn(TAG, 'Resetting the settings')
        self.settings.reset()

    async def restart_soon(self):
        # Long enough for the response to go
        await asyncio.sleep(0.3)
        Log.info(TAG, 'Restarting')
        self.platform.restart()

    async def main(self):
        from base import web
        app = web.create(self)
        port = getattr(self.platform, 'PORT', PORT)
        tasks = [asyncio.create_task(app.start_server(host=None if not MICROPYTHON else '0.0.0.0', port=port))]
        if self.light is not None:
            from base import schedule
            tasks.append(asyncio.create_task(self.light.run()))
            tasks.append(asyncio.create_task(schedule.run(self)))
        if self.mqtt.enabled:
            tasks.append(asyncio.create_task(self.mqtt.run()))
        if hasattr(self.product, 'tasks'):
            tasks += [asyncio.create_task(task) for task in self.product.tasks(self)]
        Log.info(TAG, '{} {} on port {}'.format(self.product.NAME, self.product.VERSION, port))
        await asyncio.gather(*tasks)


def run(product):
    if MICROPYTHON:
        raise NotImplementedError('The Pico layer comes in App Base step 2')
    from base import pi as platform
    device = Device(product, platform)
    asyncio.run(device.main())
