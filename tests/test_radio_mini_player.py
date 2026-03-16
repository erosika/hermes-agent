from types import SimpleNamespace

from radio import mini_player
from radio import visualizer_engine
from radio import visualizers


def test_gradient_fragments_cover_entire_row_with_multiple_theme_classes():
    fragments = mini_player._gradient_fragments("ABCDEFGH", steps=4)

    assert "".join(text for _, text in fragments) == "ABCDEFGH"
    assert [style for style, _ in fragments] == [
        "class:radio-bars-grad-0",
        "class:radio-bars-grad-1",
        "class:radio-bars-grad-2",
        "class:radio-bars-grad-3",
    ]


def test_braille_stack_returns_requested_number_of_rows():
    stack = mini_player._braille_bar_stack(1.0, rows=3)

    assert len(stack) == 3
    assert all(len(ch) == 1 for ch in stack)
    assert all(0x2800 <= ord(ch) <= 0x28FF for ch in stack)


def test_volume_knob_rotates_with_volume():
    assert mini_player._volume_knob(0) == '◜'
    assert mini_player._volume_knob(30) == '◝'
    assert mini_player._volume_knob(60) == '◞'
    assert mini_player._volume_knob(90) == '◟'


def test_volume_boxes_fill_progressively():
    assert mini_player._volume_boxes(0, cells=4) == '□□□□'
    assert mini_player._volume_boxes(50, cells=4) == '■■□□'
    assert mini_player._volume_boxes(100, cells=4) == '■■■■'


def test_generate_bars_uses_visualizer_engine(monkeypatch):
    def fake_render_rows(**kwargs):
        assert kwargs['width'] == 16
        assert kwargs['rows'] == 1
        assert kwargs['paused'] is False
        return ['X' * 16]

    monkeypatch.setattr(visualizer_engine, 'render_rows', fake_render_rows)

    bars = mini_player._generate_bars(position=1.25, title='artist-title', paused=False)

    assert bars == 'X' * 16


def test_generate_bars_expanded_uses_full_player_inner_width(monkeypatch):
    expected_width = mini_player._EXPANDED_PLAYER_WIDTH - 4

    def fake_render_rows(**kwargs):
        assert kwargs['width'] == expected_width
        assert kwargs['rows'] == 4
        assert kwargs['paused'] is True
        return ['A' * expected_width, 'B' * expected_width, 'C' * expected_width, 'D' * expected_width]

    monkeypatch.setattr(visualizer_engine, 'render_rows', fake_render_rows)
    monkeypatch.setattr(visualizers, 'load_preset', lambda name=None: {'rows': 4})

    rows = mini_player._generate_bars_expanded(position=3.0, title='seed-track', paused=True)

    assert rows == ['A' * expected_width, 'B' * expected_width, 'C' * expected_width, 'D' * expected_width]


def test_expanded_player_height_matches_rendered_line_count(monkeypatch):
    class FakeRadio:
        @classmethod
        def active(cls):
            return True

        @classmethod
        def get(cls):
            return cls()

        def now_playing(self):
            return SimpleNamespace(
                active=True,
                source_mode='crate',
                title='Track',
                artist='Artist',
                decade=1970,
                country='JPN',
                mood='fast',
                position=12.0,
                duration=100.0,
                volume=30,
                paused=False,
                station_name='Crate Digger',
            )

        @property
        def is_recording(self):
            return False

    monkeypatch.setattr('radio.player.HermesRadio', FakeRadio)
    monkeypatch.setattr(visualizers, 'load_preset', lambda name=None: {'name': 'wide', 'rows': 5})
    monkeypatch.setattr(mini_player, '_expanded', True)

    rendered = ''.join(text for _, text in mini_player.get_expanded_player_text())

    assert mini_player.get_mini_player_height() == rendered.count('\n')
