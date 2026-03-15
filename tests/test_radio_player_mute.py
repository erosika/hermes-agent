import asyncio

from radio.player import HermesRadio


class _FakePrimary:
    def __init__(self, volume=37.0):
        self.volume = volume

    async def get_volume(self):
        return self.volume

    async def set_volume(self, level):
        self.volume = level


def test_toggle_mute_round_trips_previous_volume():
    radio = HermesRadio()
    radio._primary = _FakePrimary(volume=37.0)
    radio._now.volume = 37.0

    assert asyncio.run(radio.toggle_mute()) == "Muted"
    assert radio._primary.volume == 0
    assert radio._now.volume == 0

    assert asyncio.run(radio.toggle_mute()) == "Unmuted"
    assert radio._primary.volume == 37.0
    assert radio._now.volume == 37.0
