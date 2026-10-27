import pytest

import effects


class Light:
    def speed(self):
        return 5


def grid(frame):
    """Rows of booleans: which LEDs are lit."""
    return [[any(frame[y * 8 + x]) for x in range(8)] for y in range(8)]


@pytest.mark.parametrize('mode', list(effects.MODES))
def test_every_mode_draws_64_leds_in_range(mode):
    effect = effects.MODES[mode](64, {}, Light())
    for t in (0, 1000, 5500, 9000, 20000):
        frame = effect.frame(t)
        assert len(frame) == 64
        assert all(len(p) == 3 and all(0 <= c <= 255 for c in p) for p in frame)


def test_f1_start_flashes_blue_then_lights_a_red_a_second_then_goes_out(monkeypatch):
    monkeypatch.setattr(effects.random, 'randint', lambda low, high: 1500)
    f1 = effects.F1Start(64, {}, Light())
    assert f1.frame(0)[1 * 8 + 1] == f1.BLUE
    assert not any(any(p) for p in f1.frame(700))  # the blue flashes
    reds = [sum(p == f1.RED for p in f1.frame(t)) for t in (5500, 6500, 7500, 8500, 9500, 10500)]
    assert reds == [0, 4, 8, 12, 16, 20]
    assert not f1.finished
    f1.frame(11400)
    assert not f1.finished
    assert not any(any(p) for p in f1.frame(11600)) and f1.finished


def test_the_pirate_flag_is_white_then_fills_with_red():
    flag = effects.PirateFlag(64, {}, Light())
    white = flag.frame(0)
    assert sum(p == flag.WHITE for p in white) == 23
    full = flag.frame(2000 + 10 * 200)
    assert sum(p == flag.RED for p in full) == 23
    assert sum(p == flag.RED for p in flag.frame(2000 + 100)) == 5  # the top row first


def test_cpu_chart_columns(monkeypatch):
    monkeypatch.setattr(effects, 'readings', [100, 0, 50])
    lit = grid(effects.CpuChart(64, {}, Light()).frame(0))
    column = lambda x: sum(lit[y][x] for y in range(8))
    assert [column(0), column(1), column(2), column(3)] == [8, 1, 4, 0]
    frame = effects.CpuChart(64, {}, Light()).frame(0)
    assert frame[0] == (255, 0, 0) and frame[7 * 8] == (0, 255, 0)  # the top red, the bottom green
