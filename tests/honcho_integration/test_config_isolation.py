"""Tests for Honcho config profile isolation.

Verifies that each Hermes profile writes to its own instance-local
honcho.json ($HERMES_HOME/honcho.json) rather than the shared global
~/.honcho/config.json.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from honcho_integration.cli import (
    _config_path,
    _local_config_path,
    _read_config,
    _write_config,
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Create an isolated HERMES_HOME + real home for testing."""
    hermes_home = tmp_path / "profile_a"
    hermes_home.mkdir()
    global_dir = tmp_path / "home" / ".honcho"
    global_dir.mkdir(parents=True)
    global_config = global_dir / "config.json"

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    # GLOBAL_CONFIG_PATH is a module-level constant cached at import time,
    # so we must patch it in both the defining module and the importing module.
    import honcho_integration.client as _client_mod
    import honcho_integration.cli as _cli_mod
    monkeypatch.setattr(_client_mod, "GLOBAL_CONFIG_PATH", global_config)
    monkeypatch.setattr(_cli_mod, "GLOBAL_CONFIG_PATH", global_config)

    return {
        "hermes_home": hermes_home,
        "global_config": global_config,
        "local_config": hermes_home / "honcho.json",
    }


class TestLocalConfigPath:
    """_local_config_path always returns $HERMES_HOME/honcho.json."""

    def test_returns_hermes_home_path(self, isolated_home):
        assert _local_config_path() == isolated_home["local_config"]

    def test_differs_from_global(self, isolated_home):
        from honcho_integration.client import GLOBAL_CONFIG_PATH
        assert _local_config_path() != GLOBAL_CONFIG_PATH


class TestWriteConfigIsolation:
    """_write_config defaults to the instance-local path."""

    def test_write_creates_local_file(self, isolated_home):
        cfg = {"apiKey": "test-key", "hosts": {"hermes": {"enabled": True}}}
        _write_config(cfg)

        assert isolated_home["local_config"].exists()
        written = json.loads(isolated_home["local_config"].read_text())
        assert written["apiKey"] == "test-key"

    def test_write_does_not_touch_global(self, isolated_home):
        # Pre-populate global config
        isolated_home["global_config"].write_text(
            json.dumps({"apiKey": "global-key"})
        )

        cfg = {"apiKey": "profile-key"}
        _write_config(cfg)

        # Global should be untouched
        global_data = json.loads(isolated_home["global_config"].read_text())
        assert global_data["apiKey"] == "global-key"

        # Local should have the new value
        local_data = json.loads(isolated_home["local_config"].read_text())
        assert local_data["apiKey"] == "profile-key"

    def test_explicit_path_override_still_works(self, isolated_home):
        custom = isolated_home["hermes_home"] / "custom.json"
        _write_config({"custom": True}, path=custom)
        assert custom.exists()
        assert not isolated_home["local_config"].exists()


class TestReadConfigFallback:
    """_read_config falls back through the config chain."""

    def test_reads_local_when_exists(self, isolated_home):
        isolated_home["local_config"].write_text(
            json.dumps({"source": "local"})
        )
        cfg = _read_config()
        assert cfg["source"] == "local"

    def test_falls_back_to_global(self, isolated_home):
        isolated_home["global_config"].write_text(
            json.dumps({"source": "global"})
        )
        # No local file exists
        assert not isolated_home["local_config"].exists()
        cfg = _read_config()
        assert cfg["source"] == "global"

    def test_local_takes_priority_over_global(self, isolated_home):
        isolated_home["local_config"].write_text(
            json.dumps({"source": "local"})
        )
        isolated_home["global_config"].write_text(
            json.dumps({"source": "global"})
        )
        cfg = _read_config()
        assert cfg["source"] == "local"


class TestDefaultProfileFallback:
    """Non-default profiles fall back to ~/.hermes/honcho.json (default profile config)."""

    def test_profile_reads_default_profile_config(self, tmp_path, monkeypatch):
        """A non-default profile with no local honcho.json reads ~/.hermes/honcho.json."""
        home = tmp_path / "home"
        default_hermes = home / ".hermes"
        default_hermes.mkdir(parents=True)
        profile_hermes = home / ".hermes" / "profiles" / "coder"
        profile_hermes.mkdir(parents=True)
        global_dir = home / ".honcho"
        global_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

        # Default profile has honcho.json with host blocks
        default_config = default_hermes / "honcho.json"
        default_config.write_text(json.dumps({
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice"},
                "hermes.coder": {"peerName": "alice", "aiPeer": "hermes.coder"},
            },
        }))

        # Global config has different data
        (global_dir / "config.json").write_text(json.dumps({"source": "global"}))

        import honcho_integration.client as _client_mod
        import honcho_integration.cli as _cli_mod
        monkeypatch.setattr(_client_mod, "GLOBAL_CONFIG_PATH", global_dir / "config.json")
        monkeypatch.setattr(_cli_mod, "GLOBAL_CONFIG_PATH", global_dir / "config.json")

        # Profile's HERMES_HOME points to its own dir (no honcho.json)
        monkeypatch.setenv("HERMES_HOME", str(profile_hermes))
        assert not (profile_hermes / "honcho.json").exists()

        # Should find ~/.hermes/honcho.json, not fall through to global
        cfg = _read_config()
        assert cfg.get("apiKey") == "key"
        assert "hermes.coder" in cfg.get("hosts", {})

    def test_default_profile_skips_self(self, tmp_path, monkeypatch):
        """Default profile doesn't double-read its own config."""
        home = tmp_path / "home"
        default_hermes = home / ".hermes"
        default_hermes.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        monkeypatch.setenv("HERMES_HOME", str(default_hermes))

        # No honcho.json anywhere
        import honcho_integration.client as _client_mod
        import honcho_integration.cli as _cli_mod
        global_cfg = home / ".honcho" / "config.json"
        global_cfg.parent.mkdir(parents=True)
        monkeypatch.setattr(_client_mod, "GLOBAL_CONFIG_PATH", global_cfg)
        monkeypatch.setattr(_cli_mod, "GLOBAL_CONFIG_PATH", global_cfg)

        cfg = _read_config()
        assert cfg == {}


class TestMultiProfileIsolation:
    """Two profiles writing config don't interfere with each other."""

    def test_two_profiles_get_separate_configs(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

        profile_a = tmp_path / "profile_a"
        profile_b = tmp_path / "profile_b"
        profile_a.mkdir()
        profile_b.mkdir()

        # Profile A writes its config
        monkeypatch.setenv("HERMES_HOME", str(profile_a))
        _write_config({"apiKey": "key-a", "hosts": {"hermes": {"peerName": "alice"}}})

        # Profile B writes its config
        monkeypatch.setenv("HERMES_HOME", str(profile_b))
        _write_config({"apiKey": "key-b", "hosts": {"hermes": {"peerName": "bob"}}})

        # Verify isolation
        a_data = json.loads((profile_a / "honcho.json").read_text())
        b_data = json.loads((profile_b / "honcho.json").read_text())

        assert a_data["hosts"]["hermes"]["peerName"] == "alice"
        assert b_data["hosts"]["hermes"]["peerName"] == "bob"

    def test_first_setup_seeds_from_global(self, tmp_path, monkeypatch):
        """First setup reads global config, writes to local."""
        home = tmp_path / "home"
        global_dir = home / ".honcho"
        global_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
        import honcho_integration.client as _client_mod
        import honcho_integration.cli as _cli_mod
        global_cfg_path = global_dir / "config.json"
        monkeypatch.setattr(_client_mod, "GLOBAL_CONFIG_PATH", global_cfg_path)
        monkeypatch.setattr(_cli_mod, "GLOBAL_CONFIG_PATH", global_cfg_path)

        # Existing global config
        global_config = global_dir / "config.json"
        global_config.write_text(json.dumps({
            "apiKey": "shared-key",
            "hosts": {"hermes": {"workspace": "shared-ws"}},
        }))

        profile = tmp_path / "new_profile"
        profile.mkdir()
        monkeypatch.setenv("HERMES_HOME", str(profile))

        # Read seeds from global
        cfg = _read_config()
        assert cfg["apiKey"] == "shared-key"

        # Modify and write goes to local
        cfg["hosts"]["hermes"]["peerName"] = "new-user"
        _write_config(cfg)

        local_config = profile / "honcho.json"
        assert local_config.exists()
        local_data = json.loads(local_config.read_text())
        assert local_data["hosts"]["hermes"]["peerName"] == "new-user"

        # Global unchanged
        global_data = json.loads(global_config.read_text())
        assert "peerName" not in global_data["hosts"]["hermes"]
