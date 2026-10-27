import pytest

import effects
import product


class Settings:
    def __init__(self, **chart):
        self.chart = dict({'topic': 'pc/status', 'field': 'cpu_usage', 'full_scale': 100}, **chart)

    def get(self, section, key):
        return self.chart[key]


class Device:
    def __init__(self, **chart):
        self.settings = Settings(**chart)


@pytest.fixture(autouse=True)
def no_readings(monkeypatch):
    monkeypatch.setattr(effects, 'readings', [])


def test_the_chart_topic_is_subscribed_when_set():
    assert product.mqtt_topics(Device()) == ['pc/status']
    assert product.mqtt_topics(Device(topic='')) == []


def test_readings_come_newest_first_and_eight_at_most():
    device = Device()
    for n in range(10):
        product.mqtt_message(device, 'pc/status', '{"cpu_usage": %d}' % (n * 10))
    assert effects.readings == [90, 80, 70, 60, 50, 40, 30, 20]


def test_a_reading_is_scaled_and_held_to_the_column():
    device = Device(field='load', full_scale=4)
    product.mqtt_message(device, 'pc/status', '{"load": 1}')
    product.mqtt_message(device, 'pc/status', '{"load": 9}')
    assert effects.readings == [100, 25]


def test_a_plain_number_is_a_reading_and_anything_else_is_ignored():
    device = Device()
    product.mqtt_message(device, 'pc/status', '42.5')
    product.mqtt_message(device, 'pc/status', '{"other": 1}')
    product.mqtt_message(device, 'pc/status', 'hello')
    assert effects.readings == [42.5]
