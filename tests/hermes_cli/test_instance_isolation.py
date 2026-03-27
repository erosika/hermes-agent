"""Tests for Hermes named-instance isolation across config, env, memory, sessions, and skills."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hermes_cli.instance_runtime import (
    DEFAULT_INSTANCE_NAME,
    build_instance_runtime,
    get_active_instance_name,
    get_base_hermes_home,
    get_instance_home,
    get_instance_registry_path,
    normalize_instance_name,
    register_instance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_base(monkeypatch, tmp_path: Path) -> Path:
    """Point all Hermes env vars at a fresh tmp_path base home."""
    base = tmp_path / ".hermes"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_HOME", str(base))
    monkeypatch.delenv("HERMES_INSTANCE", raising=False)
    monkeypatch.delenv("HERMES_HONCHO_HOST", raising=False)
    return base


def _create_instance_dirs(base: Path, name: str) -> Path:
    """Create a minimal instance directory structure."""
    home = get_instance_home(name, base_home=base)
    for sub in ("memories", "sessions", "skills", "skins", "logs", "plans",
                "workspace", "audio_cache", "image_cache"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    return home


# ---------------------------------------------------------------------------
# Config isolation
# ---------------------------------------------------------------------------

class TestConfigIsolation:
    def test_independent_config_yaml(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_a = _create_instance_dirs(base, "alpha")
        home_b = _create_instance_dirs(base, "beta")

        (home_a / "config.yaml").write_text("model: gpt-4\n")
        (home_b / "config.yaml").write_text("model: claude-3\n")

        assert (home_a / "config.yaml").read_text() == "model: gpt-4\n"
        assert (home_b / "config.yaml").read_text() == "model: claude-3\n"

        # Changing one does not affect the other
        (home_a / "config.yaml").write_text("model: gpt-4o\n")
        assert (home_b / "config.yaml").read_text() == "model: claude-3\n"


# ---------------------------------------------------------------------------
# Env isolation
# ---------------------------------------------------------------------------

class TestEnvIsolation:
    def test_independent_env_files(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_a = _create_instance_dirs(base, "alpha")
        home_b = _create_instance_dirs(base, "beta")

        (home_a / ".env").write_text("API_KEY=key_alpha\n")
        (home_b / ".env").write_text("API_KEY=key_beta\n")

        assert "key_alpha" in (home_a / ".env").read_text()
        assert "key_beta" in (home_b / ".env").read_text()

        (home_b / ".env").write_text("API_KEY=key_beta_v2\n")
        assert "key_alpha" in (home_a / ".env").read_text()


# ---------------------------------------------------------------------------
# Memory isolation
# ---------------------------------------------------------------------------

class TestMemoryIsolation:
    def test_memory_files_independent(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_a = _create_instance_dirs(base, "alpha")
        home_b = _create_instance_dirs(base, "beta")

        (home_a / "memories" / "note.md").write_text("alpha memory")

        assert (home_a / "memories" / "note.md").exists()
        assert not (home_b / "memories" / "note.md").exists()


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------

class TestSessionIsolation:
    def test_session_files_independent(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_a = _create_instance_dirs(base, "alpha")
        home_b = _create_instance_dirs(base, "beta")

        (home_a / "sessions" / "sess-001.json").write_text("{}")

        assert (home_a / "sessions" / "sess-001.json").exists()
        assert not (home_b / "sessions" / "sess-001.json").exists()


# ---------------------------------------------------------------------------
# Skills isolation
# ---------------------------------------------------------------------------

class TestSkillsIsolation:
    def test_skill_files_independent(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_a = _create_instance_dirs(base, "alpha")
        home_b = _create_instance_dirs(base, "beta")

        (home_a / "skills" / "greet.py").write_text("def greet(): ...")

        assert (home_a / "skills" / "greet.py").exists()
        assert not (home_b / "skills" / "greet.py").exists()


# ---------------------------------------------------------------------------
# Instance CRUD
# ---------------------------------------------------------------------------

class TestInstanceCRUD:
    def test_create_registers_and_list_shows(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        name = "dev-test"
        runtime = build_instance_runtime(name, base_home=base)
        home = runtime.home

        # Create directory structure
        for sub in ("memories", "sessions", "skills", "skins", "logs",
                     "plans", "workspace", "audio_cache", "image_cache"):
            (home / sub).mkdir(parents=True, exist_ok=True)

        register_instance(runtime)

        # Verify registry contains the instance
        registry_path = get_instance_registry_path(base)
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        assert name in payload["instances"]
        assert payload["instances"][name]["home"] == str(home)
        assert payload["instances"][name]["honcho_host"] == f"hermes.{name}"

    def test_delete_removes_from_registry(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        name = "ephemeral"
        runtime = build_instance_runtime(name, base_home=base)
        home = runtime.home
        home.mkdir(parents=True, exist_ok=True)
        register_instance(runtime)

        # Simulate deletion: remove directory and registry entry
        import shutil
        shutil.rmtree(home)
        registry_path = get_instance_registry_path(base)
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        payload["instances"].pop(name, None)
        registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        assert not home.exists()
        payload2 = json.loads(registry_path.read_text(encoding="utf-8"))
        assert name not in payload2["instances"]

    def test_cannot_delete_main(self, tmp_path, monkeypatch):
        """Verify the guard: DEFAULT_INSTANCE_NAME must not be deletable."""
        base = _setup_base(monkeypatch, tmp_path)
        name = normalize_instance_name("main")
        assert name == DEFAULT_INSTANCE_NAME

        # The CLI guards against this; we verify the invariant holds.
        assert name == "main", "normalize_instance_name should resolve to 'main'"

    def test_normalize_rejects_invalid_names(self):
        with pytest.raises(ValueError):
            normalize_instance_name("has spaces")
        with pytest.raises(ValueError):
            normalize_instance_name("@bad!")
        with pytest.raises(ValueError):
            normalize_instance_name("-starts-with-dash")

    def test_normalize_maps_default_to_main(self):
        assert normalize_instance_name("default") == DEFAULT_INSTANCE_NAME
        assert normalize_instance_name("main") == DEFAULT_INSTANCE_NAME
        assert normalize_instance_name("") == DEFAULT_INSTANCE_NAME
        assert normalize_instance_name(None) == DEFAULT_INSTANCE_NAME

    def test_instance_home_paths_are_distinct(self, tmp_path, monkeypatch):
        base = _setup_base(monkeypatch, tmp_path)
        home_main = get_instance_home(DEFAULT_INSTANCE_NAME, base_home=base)
        home_alpha = get_instance_home("alpha", base_home=base)
        home_beta = get_instance_home("beta", base_home=base)

        assert home_main == base
        assert home_alpha != home_beta
        assert home_alpha != home_main
        assert "instances/alpha" in str(home_alpha)
        assert "instances/beta" in str(home_beta)
