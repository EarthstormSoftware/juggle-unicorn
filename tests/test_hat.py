import pytest

import hat


class Settings:
    def __init__(self, rotation=0, limit=2000):
        self.values = {'rotation': rotation, 'max_current_ma': limit}

    def get(self, section, key):
        return self.values[key]


def lit_chain(unicorn, frame):
    """The chain positions lit by a frame (rpi_ws281x isn't here, so the chain is worked out the same way)."""
    unicorn.show(frame)
    return unicorn


def test_the_map_covers_every_led_once():
    assert sorted(i for row in hat.MAP for i in row) == list(range(64))


@pytest.mark.parametrize('rotation, x, y, expected', [
    (0, 1, 2, (1, 2)), (90, 1, 2, (5, 1)), (180, 1, 2, (6, 5)), (270, 1, 2, (2, 6)),
])
def test_rotation(rotation, x, y, expected):
    assert hat._rotated(x, y, rotation) == expected


def test_rotating_four_times_comes_back():
    for x in range(8):
        for y in range(8):
            p = (x, y)
            for _ in range(4):
                p = hat._rotated(*p, 90)
            assert p == (x, y)


def test_gamma_keeps_the_ends():
    assert hat.GAMMA[0] == 0 and hat.GAMMA[255] == 255 and hat.GAMMA[128] < 128


def test_a_frame_within_the_limit_is_shown_as_it_is():
    unicorn = hat.UnicornHat(Settings(limit=2000))
    unicorn.show([(255, 0, 0)] * 64)
    assert not unicorn.limited
    assert unicorn.last[0] == (255, 0, 0)
    assert unicorn.current_ma == 64 * 20 + 64


def test_a_frame_over_the_limit_is_dimmed_to_it():
    unicorn = hat.UnicornHat(Settings(limit=1200))
    unicorn.show([(255, 255, 255)] * 64)
    assert unicorn.limited
    assert unicorn.current_ma <= 1200
    assert unicorn.last[0][0] == unicorn.last[0][1] == unicorn.last[0][2] < 255


def test_the_preview_is_in_reading_order_whatever_the_rotation():
    unicorn = hat.UnicornHat(Settings(rotation=90))
    frame = [(0, 0, 0)] * 64
    frame[0] = (255, 255, 255)
    unicorn.show(frame)
    assert unicorn.last[0] == (255, 255, 255) and unicorn.last[1] == (0, 0, 0)
