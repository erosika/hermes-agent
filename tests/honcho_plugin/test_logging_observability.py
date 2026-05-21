"""Tests for the honcho memory plugin's structured logging surface.

Covers:
  - the _event() formatter contract used by every decision point
  - REASONING_COST_USD / _cost_for_level() pricing table
  - the honcho.log RotatingFileHandler installed by setup_logging() in
    both CLI and gateway modes, and its scope filter
  - hermes honcho cost aggregation against a synthetic honcho.log
  - hermes honcho watch --no-follow rendering against a synthetic log

These tests are deliberately self-contained: they construct log content
in-memory or via the real logger and assert against the resulting file or
captured stdout. No network, no Honcho SDK, no real Hermes session.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_logging_state():
    """Mirror tests/test_hermes_logging.py — strip RotatingFileHandlers and
    reset the setup_logging() sentinel before/after each test so handler
    counts and file presence are stable under xdist."""
    import hermes_logging
    hermes_logging._logging_initialized = False
    root = logging.getLogger()
    pre_existing = []
    for h in list(root.handlers):
        if isinstance(h, RotatingFileHandler):
            root.removeHandler(h)
            h.close()
        else:
            pre_existing.append(h)
    hermes_logging._install_session_record_factory()
    yield
    for h in list(root.handlers):
        if h not in pre_existing:
            root.removeHandler(h)
            h.close()
    hermes_logging._logging_initialized = False
    hermes_logging.clear_session_context()


@pytest.fixture
def hermes_home() -> Path:
    """The autouse _isolate_hermes_home fixture in conftest sets HERMES_HOME
    per test; we just read it back."""
    return Path(os.environ["HERMES_HOME"])


@pytest.fixture
def honcho_log(hermes_home) -> Path:
    """Run setup_logging() and return the path to honcho.log."""
    import hermes_logging
    hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
    return hermes_home / "logs" / "honcho.log"


# ---------------------------------------------------------------------------
# _event() formatter
# ---------------------------------------------------------------------------

class TestEventFormatter:
    def test_emits_kind_first(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("dialectic.fire", turn=3, depth=1)
        logging.shutdown()
        text = honcho_log.read_text()
        assert "[honcho.event] kind=dialectic.fire" in text

    def test_includes_all_kv_pairs(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("turn.injected", turn=5, layer1_chars=412, layer2_chars=520, total_chars=932)
        logging.shutdown()
        line = honcho_log.read_text().strip().splitlines()[-1]
        for token in ("kind=turn.injected", "turn=5", "layer1_chars=412",
                      "layer2_chars=520", "total_chars=932"):
            assert token in line, f"missing {token!r} in {line!r}"

    def test_bool_serialized_as_true_false(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("layer1.injected", turn=1, has_card=True, cold=False)
        logging.shutdown()
        line = honcho_log.read_text().strip().splitlines()[-1]
        assert "has_card=true" in line
        assert "cold=false" in line

    def test_float_serialized_with_four_decimals(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("dialectic.pass", level="medium", cost_usd=0.05)
        logging.shutdown()
        line = honcho_log.read_text().strip().splitlines()[-1]
        assert "cost_usd=0.0500" in line

    def test_string_with_spaces_is_quoted(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("dialectic.error", error="connection timed out")
        logging.shutdown()
        line = honcho_log.read_text().strip().splitlines()[-1]
        assert 'error="connection timed out"' in line

    def test_none_fields_are_skipped(self, honcho_log):
        from plugins.memory.honcho import _event
        _event("dialectic.fire", turn=1, depth=None, cadence=2)
        logging.shutdown()
        line = honcho_log.read_text().strip().splitlines()[-1]
        assert "depth=" not in line
        assert "cadence=2" in line


# ---------------------------------------------------------------------------
# Cost mapping
# ---------------------------------------------------------------------------

class TestCostMapping:
    def test_known_levels_match_pricing_table(self):
        from plugins.memory.honcho import REASONING_COST_USD, _cost_for_level
        assert _cost_for_level("minimal") == 0.001
        assert _cost_for_level("low") == 0.01
        assert _cost_for_level("medium") == 0.05
        assert _cost_for_level("high") == 0.10
        assert _cost_for_level("max") == 0.50
        assert REASONING_COST_USD == {
            "minimal": 0.001, "low": 0.01, "medium": 0.05,
            "high": 0.10, "max": 0.50,
        }

    def test_case_insensitive(self):
        from plugins.memory.honcho import _cost_for_level
        assert _cost_for_level("MEDIUM") == 0.05
        assert _cost_for_level("High") == 0.10

    def test_unknown_level_returns_zero(self):
        from plugins.memory.honcho import _cost_for_level
        assert _cost_for_level("default") == 0.0
        assert _cost_for_level("ultra") == 0.0
        assert _cost_for_level(None) == 0.0
        assert _cost_for_level("") == 0.0


# ---------------------------------------------------------------------------
# honcho.log file handler
# ---------------------------------------------------------------------------

class TestHonchoLogHandler:
    def test_creates_honcho_log_in_cli_mode(self, hermes_home):
        import hermes_logging
        log_dir = hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
        assert (log_dir / "honcho.log").exists()

    def test_creates_honcho_log_in_gateway_mode(self, hermes_home):
        import hermes_logging
        log_dir = hermes_logging.setup_logging(hermes_home=hermes_home, mode="gateway", force=True)
        files = {p.name for p in log_dir.iterdir()}
        assert "honcho.log" in files
        assert "gateway.log" in files

    def test_only_honcho_namespace_records_pass_filter(self, honcho_log):
        # honcho.* records should land here; other namespaces should not.
        logging.getLogger("plugins.memory.honcho.test").info("[honcho.event] kind=test.scoped")
        logging.getLogger("hermes_cli").info("hermes_cli noise that should not appear")
        logging.getLogger("tools.terminal").warning("tools warning that should not appear")
        logging.shutdown()
        text = honcho_log.read_text()
        assert "kind=test.scoped" in text
        assert "hermes_cli noise" not in text
        assert "tools warning" not in text

    def test_handler_is_rotating(self, hermes_home):
        import hermes_logging
        hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
        root = logging.getLogger()
        honcho_handlers = [
            h for h in root.handlers
            if isinstance(h, RotatingFileHandler)
            and Path(h.baseFilename).name == "honcho.log"
        ]
        assert len(honcho_handlers) == 1
        h = honcho_handlers[0]
        assert h.maxBytes == 5 * 1024 * 1024
        assert h.backupCount == 3
        assert h.level == logging.DEBUG

    def test_honcho_logger_forced_to_debug(self, hermes_home):
        import hermes_logging
        hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
        # Even though root is INFO by default, the honcho logger itself must
        # be at DEBUG so DEBUG records reach the honcho.log handler.
        honcho_logger = logging.getLogger("plugins.memory.honcho")
        assert honcho_logger.level == logging.DEBUG


# ---------------------------------------------------------------------------
# hermes honcho cost
# ---------------------------------------------------------------------------

@pytest.fixture
def populated_log(honcho_log):
    """Seed honcho.log with a deterministic event mix used by cost tests."""
    from plugins.memory.honcho import _event
    from hermes_logging import set_session_context, clear_session_context
    set_session_context("session-A")
    # 5 turns, 3 with dialectic fire (medium), 2 cadence-gated.
    for turn in range(1, 6):
        _event("layer1.injected", turn=turn, chars=400, has_card=True)
        if turn in (1, 3, 5):
            _event("dialectic.fire", turn=turn, depth=1, cadence=2, query_chars=80)
            _event("dialectic.pass", depth=1, pass_idx=0, level="medium",
                   cold=False, chars=500, elapsed_ms=2000, cost_usd=0.05)
            _event("dialectic.result", fired_at=turn, chars=500, elapsed_ms=2000)
            _event("layer2.injected", turn=turn, chars=500, fired_at=turn)
            _event("turn.injected", turn=turn, layer1_chars=400, layer2_chars=500,
                   total_chars=900, est_tokens=225)
        else:
            _event("dialectic.skip", reason="cadence_gate", turn=turn,
                   effective=2, since_last=1)
            _event("turn.injected", turn=turn, layer1_chars=400, layer2_chars=0,
                   total_chars=400, est_tokens=100)
    # One explicit honcho_reasoning tool call at high.
    _event("tool.honcho_reasoning", peer="user", level="high", chars=800,
           elapsed_ms=4000, turn=3, cost_usd=0.10)
    clear_session_context()
    logging.shutdown()
    return honcho_log


class TestCostCommand:
    def _run_cost(self, **kwargs) -> str:
        from plugins.memory.honcho.cli import register_cli, honcho_command
        p = argparse.ArgumentParser()
        register_cli(p)
        argv = ["cost"]
        for k, v in kwargs.items():
            argv += [f"--{k}", v]
        ns = p.parse_args(argv)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            honcho_command(ns)
        return buf.getvalue()

    def test_aggregates_total_dollar_cost(self, populated_log):
        # 3 medium passes × $0.05 + 1 high tool call × $0.10 = $0.25
        out = self._run_cost()
        assert "$0.2500" in out

    def test_breaks_down_by_reasoning_level(self, populated_log):
        out = self._run_cost()
        assert "medium" in out and "0.1500" in out  # 3 × 0.05
        assert "high" in out and "0.1000" in out    # 1 × 0.10

    def test_counts_dialectic_fires(self, populated_log):
        out = self._run_cost()
        # 3 fires out of 5 turns = 60.0%
        assert "fires            : 3" in out
        assert "60.0%" in out

    def test_counts_skips_with_reason(self, populated_log):
        out = self._run_cost()
        assert "cadence_gate" in out

    def test_aggregates_layer_chars(self, populated_log):
        out = self._run_cost()
        # 5 turns × 400 layer1
        assert "layer1 chars total : 2000" in out
        # 3 turns × 500 layer2
        assert "layer2 chars total : 1500" in out

    def test_session_filter(self, populated_log):
        # Bogus filter excludes everything → no priced calls reported.
        out = self._run_cost(session="not-a-real-session")
        assert "$0.0000" in out
        assert "turns w/ injection : 0" in out

    def test_session_filter_matches(self, populated_log):
        out = self._run_cost(session="session-A")
        assert "$0.2500" in out

    def test_handles_empty_log(self, honcho_log):
        # honcho.log exists but has no events.
        out = self._run_cost()
        assert "no events matched" in out or "$0.0000" in out


# ---------------------------------------------------------------------------
# hermes honcho watch (rendering, replay-only path)
# ---------------------------------------------------------------------------

class TestWatchCommand:
    def _run_watch(self, **flags) -> str:
        from plugins.memory.honcho.cli import register_cli, honcho_command
        p = argparse.ArgumentParser()
        register_cli(p)
        argv = ["watch", "--no-follow"]
        for k, v in flags.items():
            if v is True:
                argv += [f"--{k}"]
            elif v is not None:
                argv += [f"--{k}", str(v)]
        ns = p.parse_args(argv)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            honcho_command(ns)
        return buf.getvalue()

    def test_replays_recent_events(self, populated_log):
        out = self._run_watch(last=200)
        assert "dialectic.fire" in out
        assert "layer1.injected" in out
        assert "turn.injected" in out

    def test_filter_excludes_non_matching_kinds(self, populated_log):
        out = self._run_watch(last=200, filter="dialectic.fire")
        assert "dialectic.fire" in out
        assert "layer1.injected" not in out
        assert "turn.injected" not in out

    def test_filter_accepts_multiple_kinds(self, populated_log):
        out = self._run_watch(last=200, filter="dialectic.fire,layer1.injected")
        assert "dialectic.fire" in out
        assert "layer1.injected" in out
        assert "card.set" not in out

    def test_raw_passes_through_unmodified_lines(self, populated_log):
        out = self._run_watch(last=200, raw=True)
        # Raw should keep the full timestamp + level + namespace prefix.
        assert "plugins.memory.honcho" in out
        assert "[honcho.event]" in out

    def test_missing_log_is_created(self, hermes_home, monkeypatch):
        # Don't seed anything — watch should touch the file and exit cleanly.
        import hermes_logging
        hermes_logging.setup_logging(hermes_home=hermes_home, force=True)
        out = self._run_watch(last=0)
        assert (hermes_home / "logs" / "honcho.log").exists()
        # No events to render but no traceback either.
        assert "Traceback" not in out
