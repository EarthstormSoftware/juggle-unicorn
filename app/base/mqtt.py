"""
MQTT: the device's state and commands, and Home Assistant discovery, as PlasmaStick's, so home automation sees every
Earthstorm device the same way.

The topics hang off mqtt.topic_base ({name} is the device name) and the discovery prefix, mqtt.ha_prefix:

  <base>/status        retained: online, or offline (the will)
  <base>/info          retained: the health figures from /api/info, every minute
  <base>/state         retained, lights: {"State", "Mode", "ModeParameters", "Brightness"}, on every change
  <base>/control       lights: {"MessageType": "StateChange" | "ModeChange" | "BrightnessChange", "Parameters": {...}}
  <base>/ha/state      retained, lights: the state in Home Assistant's JSON light schema
  <base>/ha/set        lights: Home Assistant's JSON light commands
  <ha_prefix>/light/<name>/config, <ha_prefix>/sensor/<name>/<key>/config   retained discovery (if it's on)

Retained topics the device stops using (after a topic setting changes) are cleared when it next connects.

The client is the platform's (platform.mqtt_client): base.mqttclient on a Pi, mqtt_as on a Pico.
"""
from base.compat import asyncio, json
from base.log import Log
from base.settings import Setting, is_bool, is_text

TAG = 'MQTT'
ONLINE = 'online'
OFFLINE = 'offline'
DEFAULT_TOPIC_BASE = '/home/device/{name}'
DEFAULT_HA_PREFIX = 'homeassistant'
DEFAULT_PORT = 1883
INFO_INTERVAL_S = 60
MANUFACTURER = 'Earthstorm Software'
# Home Assistant gives colour temperatures in mireds (a million over kelvin): 6500 K to 2000 K
MIN_MIREDS, MAX_MIREDS = 153, 500

# The health figures Home Assistant shows as diagnostic sensors, where the platform has them: (key, name, config)
SENSORS = (
    ('uptime_s', 'Uptime', {'device_class': 'duration', 'unit_of_measurement': 's',
                            'state_class': 'total_increasing'}),
    ('temperature_c', 'Temperature', {'device_class': 'temperature', 'unit_of_measurement': '°C',
                                      'state_class': 'measurement'}),
    ('load', 'Load', {'state_class': 'measurement', 'icon': 'mdi:gauge'}),
    ('mem_free', 'Free memory', {'device_class': 'data_size', 'unit_of_measurement': 'B',
                                 'state_class': 'measurement'}),
    ('rssi', 'Wi-Fi signal', {'device_class': 'signal_strength', 'unit_of_measurement': 'dBm',
                              'state_class': 'measurement'}),
    ('ip', 'IP address', {}),
)


def _prefix_error(value, placeholder):
    if not isinstance(value, str) or not value:
        return "can't be empty"
    if len(value) > 100:
        return 'must be at most 100 characters'
    if '+' in value or '#' in value:
        return "can't contain the wildcards + or #"
    if '\0' in value:
        return "can't contain a null character"
    if value != value.strip():
        return "can't start or end with a space"
    if value.endswith('/'):
        return "can't end with /"
    if '//' in value:
        return "can't contain an empty level (//)"
    rest = value.replace('{name}', '') if placeholder else value
    if '{' in rest or '}' in rest:
        return 'only understands the placeholder {name}' if placeholder else "can't contain { or }"
    return None


def topic_base_error(value):
    return _prefix_error(value, True)


def ha_prefix_error(value):
    return _prefix_error(value, False)


def broker_error(value):
    if not isinstance(value, str) or len(value) > 100 or value != value.strip() or ' ' in value:
        return 'must be a host name or address, optionally with :port'
    try:
        broker(value)
    except ValueError as e:
        return str(e)
    return None


def broker(address):
    """(host, port) from 'host', 'host:port', or '[IPv6]:port'."""
    host, port = address, DEFAULT_PORT
    if address.startswith('['):
        host, _, rest = address[1:].partition(']')
        if rest:
            port = rest[1:]
    elif address.count(':') == 1:
        host, port = address.split(':')
    try:
        port = int(port)
    except ValueError:
        raise ValueError('has a port that isn\'t a number')
    if not 0 < port < 65536:
        raise ValueError('has a port outside 1-65535')
    return host, port


# Changing any of them reconnects with the new ones, through a restart
MQTT_SETTINGS = {
    'mqtt': {
        'enabled': Setting(False, is_bool, restart=True),
        'broker_address': Setting('', broker_error, restart=True),
        'user': Setting('', is_text(64), restart=True),
        # Kept as given (the broker needs it), but never shown
        'password': Setting('', is_text(64, allow_empty=False), restart=True, secret=True),
        'topic_base': Setting(DEFAULT_TOPIC_BASE, topic_base_error, restart=True),
        'ha_discovery': Setting(False, is_bool, restart=True),
        'ha_prefix': Setting(DEFAULT_HA_PREFIX, ha_prefix_error, restart=True),
    },
}


def topics(name, base=DEFAULT_TOPIC_BASE, ha_prefix=DEFAULT_HA_PREFIX, light=False, sensors=()):
    """The device's topics by role."""
    base = base.replace('{name}', name)
    t = {'status': base + '/status', 'info': base + '/info'}
    if light:
        t.update({
            'state': base + '/state',
            'control': base + '/control',
            'ha_state': base + '/ha/state',
            'ha_set': base + '/ha/set',
            'ha_light': ha_prefix + '/light/' + name + '/config',
        })
    for key in sensors:
        t['ha_sensor_' + key] = ha_prefix + '/sensor/' + name + '/' + key + '/config'
    return t


def retained(t):
    """The topics in t that the device publishes retained."""
    return sorted(topic for role, topic in t.items() if role not in ('control', 'ha_set'))


# Payloads

def info_payload(info):
    """The health figures from /api/info that the info topic carries."""
    payload = {'version': info['version']}
    for key, _, _ in SENSORS:
        if key in info:
            payload[key] = info[key]
    return json.dumps(payload)


def ha_state_payload(state):
    """state: Light.state(). The same in Home Assistant's JSON light schema."""
    parameters = state['ModeParameters']
    payload = {'state': 'ON' if state['State'] else 'OFF', 'color_mode': 'rgb', 'effect': state['Mode'],
               'brightness': state['Brightness']}
    kelvin = parameters.get('Kelvin')
    if kelvin:
        payload['color_mode'] = 'color_temp'
        payload['color_temp'] = (1000000 + kelvin // 2) // kelvin
    colour = parameters.get('Colour')
    if colour:
        digits = colour.lstrip('#')
        payload['color'] = {'r': int(digits[0:2], 16), 'g': int(digits[2:4], 16), 'b': int(digits[4:6], 16)}
    return json.dumps(payload)


def _device(name, product):
    d = {'identifiers': [name], 'name': name, 'manufacturer': getattr(product, 'MANUFACTURER', MANUFACTURER),
         'model': getattr(product, 'MODEL', product.NAME), 'sw_version': product.VERSION}
    return d


def ha_light_payload(name, t, product, modes):
    return json.dumps({
        'name': None,  # the entity takes the device's name
        'unique_id': name + '_light',
        'schema': 'json',
        'command_topic': t['ha_set'],
        'state_topic': t['ha_state'],
        'availability_topic': t['status'],
        'supported_color_modes': ['rgb', 'color_temp'],
        'min_mireds': MIN_MIREDS,
        'max_mireds': MAX_MIREDS,
        'brightness': True,
        'brightness_scale': 100,  # percent, as the device has it
        'effect': True,
        'effect_list': list(modes),
        'device': _device(name, product),
    })


def ha_sensor_payload(name, t, product, key):
    for k, title, extra in SENSORS:
        if k == key:
            config = {
                'name': title,
                'unique_id': name + '_' + key,
                'state_topic': t['info'],
                'value_template': '{{ value_json.' + key + ' }}',
                'availability_topic': t['status'],
                'entity_category': 'diagnostic',
                'device': _device(name, product),
            }
            config.update(extra)
            return json.dumps(config)
    raise ValueError('unknown sensor')


# Commands, as keyword arguments for Light.set

def _number(value, low, high, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError('{} must be {}-{}'.format(what, low, high))
    return value


def parse_control(payload):
    """A control message (PlasmaStick's): StateChange, ModeChange or BrightnessChange. Raises ValueError."""
    if not isinstance(payload, dict):
        raise ValueError('a control message must be a JSON object')
    kind = payload.get('MessageType')
    parameters = payload.get('Parameters') or {}
    if not isinstance(parameters, dict):
        raise ValueError('Parameters must be an object')
    if kind == 'StateChange':
        if not isinstance(parameters.get('State'), bool):
            raise ValueError('State must be true or false')
        return {'on': parameters['State']}
    if kind == 'ModeChange':
        return {'mode': parameters.get('Mode'), 'parameters': parameters.get('ModeParameters')}
    if kind == 'BrightnessChange':
        return {'brightness': parameters.get('Brightness')}
    raise ValueError('unknown MessageType {}'.format(kind))


def parse_ha_command(payload, modes):
    """A Home Assistant JSON light command. Raises ValueError for anything it can't use."""
    if not isinstance(payload, dict):
        raise ValueError('a command must be a JSON object')
    change = {}
    colour, effect = payload.get('color'), payload.get('effect')
    if colour is not None:
        try:
            r, g, b = (int(colour[k]) for k in ('r', 'g', 'b'))
        except (KeyError, TypeError, ValueError):
            raise ValueError('color needs r, g and b')
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError('color values must be 0-255')
        change.update(mode='Colour', parameters={'Colour': '#{:02x}{:02x}{:02x}'.format(r, g, b)})
    elif payload.get('color_temp') is not None:
        mireds = _number(payload['color_temp'], 100, 1000, 'color_temp')
        change.update(mode='Colour', parameters={'Kelvin': min(6500, max(2000, int(1000000 / mireds + 0.5)))})
    elif effect is not None:
        if effect not in modes:
            raise ValueError('unknown effect')
        change['mode'] = effect
    if payload.get('brightness') is not None:
        change['brightness'] = max(1, int(_number(payload['brightness'], 0, 100, 'brightness') + 0.5))
    state = payload.get('state')
    if state is not None:
        if state not in ('ON', 'OFF'):
            raise ValueError('state must be ON or OFF')
        change['on'] = state == 'ON'
    if not change:
        raise ValueError('nothing to do')
    if payload.get('transition') is not None:
        change['transition_ms'] = int(_number(payload['transition'], 0, 3600, 'transition') * 1000 + 0.5)
    return change


def failure(e):
    """Why connecting failed, for the page."""
    if isinstance(e, asyncio.TimeoutError):
        return "The broker didn't answer in time."
    if isinstance(e, ConnectionRefusedError):
        return 'The broker refused the connection: is it running, and on that port?'
    text = str(e) or e.__class__.__name__
    if 'getaddrinfo' in text or 'Name or service' in text or 'nodename' in text:
        return "The broker's address wasn't found."
    return 'Could not connect: ' + text[:1].upper() + text[1:] + ('' if text.endswith('.') else '.')


class Mqtt:
    def __init__(self, device):
        self.device = device
        s = device.settings
        self.enabled = s.get('mqtt', 'enabled') and bool(s.get('mqtt', 'broker_address'))
        self.connected = False
        self.error = None
        self.name = device.platform.device_name()
        self.ha = s.get('mqtt', 'ha_discovery')
        self.light = device.light
        info = device.info()
        self.sensors = tuple(key for key, _, _ in SENSORS if info.get(key) is not None)
        self.topics = topics(self.name, s.get('mqtt', 'topic_base'), s.get('mqtt', 'ha_prefix'),
                             light=self.light is not None, sensors=self.sensors)
        self._changed = asyncio.Event()
        if self.light is not None:
            self.light.listeners.append(lambda light: self._changed.set())

    def status(self):
        return {'enabled': self.enabled, 'connected': self.connected, 'error': self.error}

    async def run(self):
        if not self.enabled:
            return
        s = self.device.settings
        host, port = broker(s.get('mqtt', 'broker_address'))
        wait = 1
        while True:
            client = self.device.platform.mqtt_client(
                client_id=self.name, host=host, port=port, user=s.get('mqtt', 'user'),
                password=s.get('mqtt', 'password'), will=(self.topics['status'], OFFLINE, True))
            tasks = []
            try:
                await client.connect()
                self.connected, self.error, wait = True, None, 1
                Log.info(TAG, 'Connected to {}:{}'.format(host, port))
                await self._up(client)
                tasks = [asyncio.create_task(self._publish_state(client)),
                         asyncio.create_task(self._publish_info(client))]
                await self._receive(client)
                self.error = 'The connection to the broker dropped.'
            except Exception as e:  # anything a broker, or the network, can do: try again
                self.error = failure(e)
            finally:
                self.connected = False
                for task in tasks:
                    task.cancel()
                client.close()
            Log.warn(TAG, '{} Trying again in {} s'.format(self.error, wait))
            await asyncio.sleep(wait)
            wait = min(wait * 2, 60)

    async def _up(self, client):
        t = self.topics
        await client.publish(t['status'], ONLINE, retain=True)
        await self._clear_retired(client)
        # With discovery off, an empty retained config removes any earlier one from Home Assistant
        if self.light is not None:
            await client.subscribe(t['control'])
            if self.ha:
                await client.subscribe(t['ha_set'])
            await client.publish(t['ha_light'], ha_light_payload(self.name, t, self.device.product, self.light.modes)
                                 if self.ha else '', retain=True)
        for key in self.sensors:
            await client.publish(t['ha_sensor_' + key], ha_sensor_payload(self.name, t, self.device.product, key)
                                 if self.ha else '', retain=True)
        await self._send_info(client)
        self._changed.set()  # the state, now it's connected

    async def _clear_retired(self, client):
        """Empties retained topics the device used before and doesn't now (a topic setting changed)."""
        path = self.device.platform.state_path('mqtt-topics.json')
        current = retained(self.topics)
        try:
            with open(path) as f:
                before = json.loads(f.read())
        except (OSError, ValueError):
            before = []
        retired = [topic for topic in before if topic not in current]
        for topic in retired:
            await client.publish(topic, '', retain=True)
        if retired:
            Log.info(TAG, 'Cleared {} old retained topic(s)'.format(len(retired)))
        if before != current:
            from base.compat import write_atomically
            write_atomically(path, json.dumps(current))

    async def _send_info(self, client):
        await client.publish(self.topics['info'], info_payload(self.device.info()), retain=True)

    # A publish that fails closes the connection, so run() connects again

    async def _publish_info(self, client):
        try:
            while True:
                await asyncio.sleep(INFO_INTERVAL_S)
                await self._send_info(client)
        except OSError:
            client.close()

    async def _publish_state(self, client):
        if self.light is None:
            return
        try:
            while True:
                await self._changed.wait()
                self._changed.clear()
                state = self.light.state()
                await client.publish(self.topics['state'], json.dumps(state), retain=True)
                if self.ha:
                    await client.publish(self.topics['ha_state'], ha_state_payload(state), retain=True)
        except OSError:
            client.close()

    async def _receive(self, client):
        while True:
            message = await client.message()
            if message is None:
                return
            topic, text, _ = message
            Log.debug(TAG, '{}: {}'.format(topic, text))
            try:
                payload = json.loads(text)
                if topic == self.topics.get('control'):
                    change = parse_control(payload)
                elif topic == self.topics.get('ha_set'):
                    change = parse_ha_command(payload, self.light.modes)
                else:
                    continue
            except ValueError as e:
                Log.warn(TAG, 'Ignoring a message on {}: {}'.format(topic, e))
                continue
            error = self.light.set(**change)
            if error:
                Log.warn(TAG, 'Ignoring a message on {}: {}'.format(topic, error))
