"""Tests for Hermes named instance runtime bootstrap and registry."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hermes_cli.instance_runtime import (
    DEFAULT_INSTANCE_NAME,
    bootstrap_instance_env,
    get_active_honcho_host,
    get_active_instance_name,
    get_base_hermes_home,
    get_instance_home,
    get_instance_registry_path,
    resolve_honcho_host,
)


def test_get_instance_home_uses_base_home_for_default_instance(tmp_path):
    assert get_instance_home(DEFAULT_INSTANCE_NAME, base_home=tmp_path) == tmp_path


def test_get_instance_home_uses_instances_dir_for_named_instance(tmp_path):
    assert get_instance_home("dreamer", base_home=tmp_path) == tmp_path / "instances" / "dreamer"


def test_resolve_honcho_host_uses_plain_hermes_for_default():
    assert resolve_honcho_host(DEFAULT_INSTANCE_NAME) == "hermes"


def test_resolve_honcho_host_scopes_named_instances():
    assert resolve_honcho_host("dreamer") == "hermes.dreamer"


def test_bootstrap_instance_env_strips_instance_flag_anywhere_and_sets_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_BASE_HOME", raising=False)
    monkeypatch.delenv("HERMES_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)

    processed = bootstrap_instance_env(["gateway", "start", "--instance", "dreamer", "--system"])

    expected_base = tmp_path / ".hermes"
    expected_home = expected_base / "instances" / "dreamer"

    assert processed == ["gateway", "start", "--system"]
    assert Path(os.environ["HERMES_BASE_HOME"]) == expected_base
    assert Path(os.environ["HERMES_HOME"]) == expected_home
    assert os.environ["HERMES_INSTANCE"] == "dreamer"
    assert os.environ["HERMES_HONCHO_HOST"] == "hermes.dreamer"


def test_bootstrap_instance_env_supports_equals_syntax(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_BASE_HOME", raising=False)
    monkeypatch.delenv("HERMES_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)

    processed = bootstrap_instance_env(["--instance=treasurer", "chat", "-q", "hi"])

    assert processed == ["chat", "-q", "hi"]
    assert os.environ["HERMES_INSTANCE"] == "treasurer"
    assert os.environ["HERMES_HONCHO_HOST"] == "hermes.treasurer"


def test_bootstrap_instance_env_keeps_default_instance_when_no_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_BASE_HOME", raising=False)
    monkeypatch.delenv("HERMES_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)

    processed = bootstrap_instance_env(["chat"])

    expected_base = tmp_path / ".hermes"
    assert processed == ["chat"]
    assert Path(os.environ["HERMES_HOME"]) == expected_base
    assert Path(os.environ["HERMES_BASE_HOME"]) == expected_base
    assert os.environ["HERMES_INSTANCE"] == DEFAULT_INSTANCE_NAME
    assert os.environ["HERMES_HONCHO_HOST"] == "hermes"


def test_bootstrap_instance_env_registers_active_instance(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_BASE_HOME", raising=False)
    monkeypatch.delenv("HERMES_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)

    bootstrap_instance_env(["--instance", "dreamer", "chat"])

    registry_path = get_instance_registry_path()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = payload["instances"]["dreamer"]

    assert entry["home"] == str(tmp_path / ".hermes" / "instances" / "dreamer")
    assert entry["honcho_host"] == "hermes.dreamer"


def test_get_base_home_and_active_values_derive_from_env(monkeypatch, tmp_path):
    base_home = tmp_path / "hermes-root"
    named_home = base_home / "instances" / "director"
    monkeypatch.setenv("HERMES_HOME", str(named_home))
    monkeypatch.setenv("HERMES_INSTANCE", "director")
    monkeypatch.delenv("HERMES_BASE_HOME", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)

    assert get_base_hermes_home() == base_home
    assert get_active_instance_name() == "director"
    assert get_active_honcho_host() == "hermes.director"


def test_bootstrap_rejects_missing_instance_value(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="requires a value"):
        bootstrap_instance_env(["chat", "--instance"])
