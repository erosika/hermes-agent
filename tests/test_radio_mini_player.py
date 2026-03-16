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


def test_generate_bars_expanded_uses_visualizer_engine(monkeypatch):
    def fake_render_rows(**kwargs):
        assert kwargs['width'] == 52
        assert kwargs['rows'] == 4
        assert kwargs['paused'] is True
        return ['A' * 52, 'B' * 52, 'C' * 52, 'D' * 52]

    monkeypatch.setattr(visualizer_engine, 'render_rows', fake_render_rows)
    monkeypatch.setattr(visualizers, 'load_preset', lambda name=None: {'rows': 4})

    rows = mini_player._generate_bars_expanded(position=3.0, title='seed-track', paused=True)

    assert rows == ['A' * 52, 'B' * 52, 'C' * 52, 'D' * 52]
