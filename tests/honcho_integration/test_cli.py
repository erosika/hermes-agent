"""Tests for Honcho CLI commands with named Hermes instances."""

from __future__ import annotations

import json
from types import SimpleNamespace

import honcho_integration.cli as honcho_cli


def test_cmd_peer_writes_to_active_instance_host_block(tmp_path, monkeypatch):
    config_path = tmp_path / "honcho.json"
    config_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_INSTANCE", "dreamer")
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)
    monkeypatch.setattr(honcho_cli, "_config_path", lambda: config_path)

    honcho_cli.cmd_peer(SimpleNamespace(user="eri", ai="dreamer", reasoning=None))

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["hosts"]["hermes.dreamer"]["peerName"] == "eri"
    assert payload["hosts"]["hermes.dreamer"]["aiPeer"] == "dreamer"


def test_cmd_mode_writes_memory_mode_to_active_instance_host_block(tmp_path, monkeypatch):
    config_path = tmp_path / "honcho.json"
    config_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_INSTANCE", "treasurer")
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)
    monkeypatch.setattr(honcho_cli, "_config_path", lambda: config_path)

    honcho_cli.cmd_mode(SimpleNamespace(mode="honcho"))

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["hosts"]["hermes.treasurer"]["memoryMode"] == "honcho"
