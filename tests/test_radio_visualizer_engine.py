from collections import deque

from radio import level_meter


def test_feature_snapshot_returns_safe_defaults_when_meter_inactive(monkeypatch):
    monkeypatch.setattr(level_meter, '_levels', deque([], maxlen=64))
    monkeypatch.setattr(level_meter, '_running', False)
    monkeypatch.setattr(level_meter, '_process', None)

    snap = level_meter.get_feature_snapshot(16)

    assert snap.levels == [0.0] * 16
    assert snap.energy == 0.0
    assert snap.peak == 0.0
    assert snap.transient == 0.0
    assert snap.motion == 0.0
    assert snap.decay == 0.0
    assert snap.active is False


def test_feature_snapshot_resamples_recent_levels_and_computes_motion(monkeypatch):
    monkeypatch.setattr(level_meter, '_levels', deque([-50.0, -40.0, -20.0, -10.0], maxlen=64))
    monkeypatch.setattr(level_meter, '_running', True)

    class _Proc:
        def poll(self):
            return None

    monkeypatch.setattr(level_meter, '_process', _Proc())

    snap = level_meter.get_feature_snapshot(8)

    assert len(snap.levels) == 8
    assert all(0.0 <= value <= 1.0 for value in snap.levels)
    assert 0.0 <= snap.energy <= 1.0
    assert 0.0 <= snap.peak <= 1.0
    assert snap.motion > 0.0
    assert snap.transient > 0.0
    assert snap.decay >= 0.0
    assert snap.active is True


def test_render_rows_returns_requested_dimensions():
    from radio.visualizer_engine import render_rows

    rows = render_rows(
        preset_name='braille',
        width=16,
        rows=3,
        paused=False,
        position=0.0,
        title_seed='test-track',
    )

    assert len(rows) == 3
    assert all(len(row) == 16 for row in rows)


def test_render_rows_returns_strings_even_when_meter_inactive(monkeypatch):
    from radio import visualizer_engine

    monkeypatch.setattr(
        visualizer_engine,
        'get_feature_snapshot',
        lambda width, smoothing=0.0: level_meter.VisualizerFeatures(
            levels=[0.0] * width,
            energy=0.0,
            peak=0.0,
            transient=0.0,
            motion=0.0,
            decay=0.0,
            active=False,
        ),
    )

    rows = visualizer_engine.render_rows(
        preset_name='braille',
        width=12,
        rows=2,
        paused=False,
        position=4.2,
        title_seed='fallback-seed',
    )

    assert len(rows) == 2
    assert all(isinstance(row, str) for row in rows)
    assert all(len(row) == 12 for row in rows)


def test_default_visualizer_is_wide_when_config_missing(tmp_path, monkeypatch):
    from radio import config as radio_config

    monkeypatch.setattr(radio_config, 'RADIO_DIR', tmp_path)
    monkeypatch.setattr(radio_config, 'CONFIG_PATH', tmp_path / 'config.yaml')

    assert radio_config.get_visualizer() == 'wide'


def test_visualizer_name_round_trips_through_radio_config(tmp_path, monkeypatch):
    from radio import config as radio_config

    monkeypatch.setattr(radio_config, 'RADIO_DIR', tmp_path)
    monkeypatch.setattr(radio_config, 'CONFIG_PATH', tmp_path / 'config.yaml')

    radio_config.set_visualizer('mirror')

    assert radio_config.get_visualizer() == 'mirror'


def test_cycle_preset_wraps_and_persists(tmp_path, monkeypatch):
    from radio import config as radio_config
    from radio import visualizers

    monkeypatch.setattr(radio_config, 'RADIO_DIR', tmp_path)
    monkeypatch.setattr(radio_config, 'CONFIG_PATH', tmp_path / 'config.yaml')
    monkeypatch.setattr(visualizers, 'list_presets', lambda: ['braille', 'mirror', 'wide'])

    radio_config.set_visualizer('wide')
    assert visualizers.cycle_preset(1) == 'braille'
    assert radio_config.get_visualizer() == 'braille'
    assert visualizers.cycle_preset(-1) == 'wide'


def test_build_menu_items_includes_visualizer_presets(monkeypatch):
    from radio import menu

    monkeypatch.setattr(menu, 'list_presets', lambda: ['braille', 'mirror'])

    items = menu.build_menu_items(active_visualizer='mirror')

    visualizer_items = [item for item in items if item.action == 'visualizer']
    assert [item.data['name'] for item in visualizer_items] == ['braille', 'mirror']
    assert visualizer_items[1].sublabel == 'active'


def test_build_menu_items_places_visualizer_and_options_before_crate_sections(monkeypatch):
    from radio import menu

    monkeypatch.setattr(menu, 'list_presets', lambda: ['wide'])
    items = menu.build_menu_items(active_visualizer='wide')
    labels = [item.label for item in items]

    assert labels.index('VISUALIZER') < labels.index('CRATE DIGGER')
    assert labels.index('OPTIONS') < labels.index('CRATE DIGGER')


def test_mirror_mode_is_horizontally_symmetric_even_without_mirror_flag(monkeypatch):
    from radio import visualizer_engine

    monkeypatch.setattr(
        visualizer_engine,
        'load_preset',
        lambda name=None: {
            'name': 'mirror',
            'mode': 'mirror',
            'chars': 'ascii',
            'rows': 1,
            'width': 5,
            'attack': 100.0,
            'decay': 100.0,
            'center_boost': 0.0,
            'mirror': False,
        },
    )
    monkeypatch.setattr(
        visualizer_engine,
        'get_feature_snapshot',
        lambda width, smoothing=0.0: level_meter.VisualizerFeatures(
            levels=[0.1, 0.2, 0.7, 1.0, 0.3][:width],
            energy=0.5,
            peak=1.0,
            transient=0.2,
            motion=0.3,
            decay=0.0,
            active=True,
        ),
    )

    row = visualizer_engine.render_rows(
        preset_name='mirror',
        width=5,
        rows=1,
        paused=False,
        position=0.0,
        title_seed='mirror-seed',
    )[0]

    assert row == row[::-1]


def test_builtin_mirror_preset_uses_dedicated_mirror_scene():
    from radio import visualizers

    preset = visualizers.load_preset('mirror')

    assert preset['scene'] == 'mirror'


def test_braille_scene_is_distinct_from_plain_bars():
    from radio import visualizer_engine

    grid = visualizer_engine.TerminalGrid(cols=20, rows=4)
    state = visualizer_engine.VisualizerState()
    features = level_meter.VisualizerFeatures(
        levels=[0.15, 0.25, 0.4, 0.7, 0.95, 0.75, 0.55, 0.35, 0.2, 0.1],
        energy=0.68,
        peak=0.95,
        transient=0.42,
        motion=0.37,
        decay=0.06,
        active=True,
    )
    levels = visualizer_engine._resample_levels(features.levels, grid.cols)

    braille_field = visualizer_engine._compose_scene(
        'braille',
        grid,
        levels,
        features,
        state,
        {'detail': 1.4},
        'braille-seed',
    )
    plain_bars = visualizer_engine._scene_bars(grid, levels, features, state, 1.4)

    assert braille_field != plain_bars
    assert sum(braille_field[0]) > 0.0


def test_builtin_scatter_preset_keeps_dot_glyphs_for_circle_texture():
    from radio import visualizers

    preset = visualizers.load_preset('scatter')

    assert preset['chars'] == 'dots'


def test_scatter_mode_uses_transient_features_instead_of_fallback_bars(monkeypatch):
    from radio import visualizer_engine

    monkeypatch.setattr(
        visualizer_engine,
        'load_preset',
        lambda name=None: {
            'name': 'scatter',
            'mode': 'scatter',
            'chars': 'dots',
            'rows': 3,
            'width': 12,
            'attack': 100.0,
            'decay': 100.0,
            'center_boost': 0.0,
            'mirror': False,
        },
    )
    monkeypatch.setattr(
        visualizer_engine,
        'get_feature_snapshot',
        lambda width, smoothing=0.0: level_meter.VisualizerFeatures(
            levels=[0.0] * width,
            energy=0.2,
            peak=0.3,
            transient=1.0,
            motion=0.5,
            decay=0.0,
            active=True,
        ),
    )
    monkeypatch.setattr(
        visualizer_engine,
        '_synthetic_snapshot',
        lambda width, position, title_seed: level_meter.VisualizerFeatures(
            levels=[0.0] * width,
            energy=0.0,
            peak=0.0,
            transient=0.0,
            motion=0.0,
            decay=0.0,
            active=False,
        ),
    )

    rows = visualizer_engine.render_rows(
        preset_name='scatter',
        width=12,
        rows=3,
        paused=False,
        position=0.0,
        title_seed='scatter-seed',
    )

    assert ''.join(rows).strip()


def test_cathedral_scene_produces_nonempty_layered_output(monkeypatch):
    from radio import visualizer_engine

    monkeypatch.setattr(
        visualizer_engine,
        'load_preset',
        lambda name=None: {
            'name': 'cathedral',
            'scene': 'cathedral',
            'mode': 'cathedral',
            'chars': 'hybrid',
            'rows': 4,
            'width': 16,
            'attack': 100.0,
            'decay': 100.0,
            'center_boost': 0.2,
            'mirror': True,
            'trail': 0.2,
            'pulse_gain': 1.0,
            'gamma': 0.8,
            'floor': 0.02,
            'contrast': 1.1,
            'detail': 1.2,
            'blur': 0,
        },
    )
    monkeypatch.setattr(
        visualizer_engine,
        'get_feature_snapshot',
        lambda width, smoothing=0.0: level_meter.VisualizerFeatures(
            levels=[0.15, 0.3, 0.55, 0.8, 1.0, 0.8, 0.55, 0.3, 0.15][:width],
            energy=0.72,
            peak=1.0,
            transient=0.45,
            motion=0.35,
            decay=0.08,
            active=True,
        ),
    )

    rows = visualizer_engine.render_rows(
        preset_name='cathedral',
        width=16,
        rows=4,
        paused=False,
        position=2.0,
        title_seed='cathedral-seed',
    )

    assert len(rows) == 4
    assert all(len(row) == 16 for row in rows)
    assert ''.join(rows).strip()
    assert len(set(''.join(rows))) > 3


def test_plasma_scene_uses_multiple_density_levels(monkeypatch):
    from radio import visualizer_engine

    monkeypatch.setattr(
        visualizer_engine,
        'load_preset',
        lambda name=None: {
            'name': 'plasma',
            'scene': 'plasma',
            'mode': 'plasma',
            'chars': 'ascii',
            'rows': 3,
            'width': 18,
            'attack': 100.0,
            'decay': 100.0,
            'center_boost': 0.0,
            'mirror': False,
            'trail': 0.4,
            'pulse_gain': 0.8,
            'gamma': 0.7,
            'floor': 0.02,
            'contrast': 1.2,
            'detail': 1.3,
            'blur': 1,
        },
    )
    monkeypatch.setattr(
        visualizer_engine,
        'get_feature_snapshot',
        lambda width, smoothing=0.0: level_meter.VisualizerFeatures(
            levels=[0.2, 0.4, 0.9, 0.7, 0.3, 0.1, 0.5, 0.85, 0.65, 0.25][:width],
            energy=0.68,
            peak=0.95,
            transient=0.3,
            motion=0.55,
            decay=0.04,
            active=True,
        ),
    )

    rows = visualizer_engine.render_rows(
        preset_name='plasma',
        width=18,
        rows=3,
        paused=False,
        position=1.5,
        title_seed='plasma-seed',
    )

    glyphs = set(''.join(rows))
    assert len(rows) == 3
    assert all(len(row) == 18 for row in rows)
    assert ''.join(rows).strip()
    assert len(glyphs - {' '}) >= 4
