"""Tests for Honcho profile capabilities (PR #4616).

Covers: clone_honcho_for_profile, cmd_enable, cmd_disable, cmd_sync,
cmd_status --all, cmd_peers, _host_key, _all_profile_host_configs,
--target-profile flag, and honcho_command routing.
"""

import json
import os
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from honcho_integration.cli import (
    _host_key,
    _all_profile_host_configs,
    _read_config,
    _write_config,
    clone_honcho_for_profile,
    cmd_enable,
    cmd_disable,
    cmd_sync,
    cmd_peers,
    honcho_command,
    sync_honcho_profiles_quiet,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


class FakeProfile:
    def __init__(self, name):
        self.name = name
        self.is_default = name == "default"


@pytest.fixture
def honcho_env(tmp_path, monkeypatch):
    """Isolated Honcho config environment for testing."""
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    config_file = hermes_home / "honcho.json"

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    # Patch _config_path and _local_config_path to use our temp file
    monkeypatch.setattr(
        "honcho_integration.cli._config_path", lambda: config_file
    )
    monkeypatch.setattr(
        "honcho_integration.cli._local_config_path", lambda: config_file
    )
    # Prevent real peer creation
    monkeypatch.setattr(
        "honcho_integration.cli._ensure_peer_exists", lambda host_key=None: True
    )

    return {"config_file": config_file, "hermes_home": hermes_home}


def _write_cfg(path, data):
    path.write_text(json.dumps(data, indent=2))


def _read_cfg(path):
    return json.loads(path.read_text())


# ── _host_key() ─────────────────────────────────────────────────────────────


class TestHostKey:
    def test_default_profile_returns_hermes(self, monkeypatch):
        import honcho_integration.cli as mod
        monkeypatch.setattr(mod, "_profile_override", None)
        with patch("honcho_integration.cli.resolve_active_host", return_value="hermes"):
            assert _host_key() == "hermes"

    def test_profile_override_default_returns_base_host(self, monkeypatch):
        import honcho_integration.cli as mod
        monkeypatch.setattr(mod, "_profile_override", "default")
        assert _host_key() == "hermes"

    def test_profile_override_custom_returns_base_host(self, monkeypatch):
        import honcho_integration.cli as mod
        monkeypatch.setattr(mod, "_profile_override", "custom")
        assert _host_key() == "hermes"

    def test_profile_override_named_returns_scoped(self, monkeypatch):
        import honcho_integration.cli as mod
        monkeypatch.setattr(mod, "_profile_override", "coder")
        assert _host_key() == "hermes.coder"

    def test_no_override_delegates_to_resolve(self, monkeypatch):
        import honcho_integration.cli as mod
        monkeypatch.setattr(mod, "_profile_override", None)
        with patch("honcho_integration.cli.resolve_active_host", return_value="hermes.dreamer"):
            assert _host_key() == "hermes.dreamer"


# ── _all_profile_host_configs() ─────────────────────────────────────────────


class TestAllProfileHostConfigs:
    def test_returns_default_and_named_profiles(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice"},
                "hermes.coder": {"peerName": "alice-code"},
            },
        })

        profiles = [FakeProfile("default"), FakeProfile("coder")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles), \
             patch("honcho_integration.cli._active_profile_name", return_value="default"):
            rows = _all_profile_host_configs()

        assert len(rows) == 2
        names = [r[0] for r in rows]
        assert "default" in names
        assert "coder" in names

        # Default profile should have its host block
        default_row = [r for r in rows if r[0] == "default"][0]
        assert default_row[1] == "hermes"
        assert default_row[2].get("peerName") == "alice"

        # Coder profile gets hermes.coder
        coder_row = [r for r in rows if r[0] == "coder"][0]
        assert coder_row[1] == "hermes.coder"
        assert coder_row[2].get("peerName") == "alice-code"

    def test_missing_host_block_returns_empty_dict(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"peerName": "alice"}},
        })

        profiles = [FakeProfile("default"), FakeProfile("newprofile")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles), \
             patch("honcho_integration.cli._active_profile_name", return_value="default"):
            rows = _all_profile_host_configs()

        new_row = [r for r in rows if r[0] == "newprofile"][0]
        assert new_row[1] == "hermes.newprofile"
        assert new_row[2] == {}  # no host block yet

    def test_profiles_import_failure_returns_active_only(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {"apiKey": "key"})

        with patch("honcho_integration.cli._active_profile_name", return_value="default"), \
             patch("hermes_cli.profiles.list_profiles", side_effect=ImportError("nope")):
            rows = _all_profile_host_configs()

        assert len(rows) == 1
        assert rows[0][0] == "default"


# ── cmd_enable ──────────────────────────────────────────────────────────────


class TestCmdEnable:
    def test_enables_existing_profile(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes.coder": {"enabled": False, "aiPeer": "hermes.coder"}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes.coder")

        cmd_enable(SimpleNamespace())

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.coder"]["enabled"] is True
        output = capsys.readouterr().out
        assert "enabled" in output.lower()

    def test_already_enabled_prints_message(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": True, "aiPeer": "hermes"}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes")

        cmd_enable(SimpleNamespace())

        output = capsys.readouterr().out
        assert "already enabled" in output.lower()

    def test_enable_new_profile_clones_from_default(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {
                    "memoryMode": "honcho",
                    "recallMode": "tools",
                    "peerName": "alice",
                    "workspace": "shared",
                },
            },
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes.writer")

        cmd_enable(SimpleNamespace())

        cfg = _read_cfg(honcho_env["config_file"])
        block = cfg["hosts"]["hermes.writer"]
        assert block["enabled"] is True
        assert block["memoryMode"] == "honcho"
        assert block["recallMode"] == "tools"
        assert block["peerName"] == "alice"
        assert block["aiPeer"] == "writer"
        assert block["workspace"] == "shared"


# ── cmd_disable ─────────────────────────────────────────────────────────────


class TestCmdDisable:
    def test_disables_profile(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes.coder": {"enabled": True}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes.coder")

        cmd_disable(SimpleNamespace())

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.coder"]["enabled"] is False

    def test_already_disabled_prints_message(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": False}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes")

        cmd_disable(SimpleNamespace())

        output = capsys.readouterr().out
        assert "already disabled" in output.lower()

    def test_disable_nonexistent_block_prints_message(self, honcho_env, capsys, monkeypatch):
        _write_cfg(honcho_env["config_file"], {"apiKey": "key", "hosts": {}})
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes.ghost")

        cmd_disable(SimpleNamespace())

        output = capsys.readouterr().out
        assert "already disabled" in output.lower()


# ── cmd_sync ────────────────────────────────────────────────────────────────


class TestCmdSync:
    def test_syncs_new_profiles(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"peerName": "alice", "memoryMode": "honcho"}},
        })

        profiles = [FakeProfile("default"), FakeProfile("coder"), FakeProfile("dreamer")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            cmd_sync(SimpleNamespace())

        cfg = _read_cfg(honcho_env["config_file"])
        assert "hermes.coder" in cfg["hosts"]
        assert "hermes.dreamer" in cfg["hosts"]

        output = capsys.readouterr().out
        assert "coder" in output
        assert "dreamer" in output
        assert "2 profile(s) synced" in output

    def test_sync_skips_already_configured(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice"},
                "hermes.coder": {"peerName": "existing"},
            },
        })

        profiles = [FakeProfile("default"), FakeProfile("coder")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            cmd_sync(SimpleNamespace())

        output = capsys.readouterr().out
        assert "All profiles already have Honcho config" in output

    def test_sync_with_no_config_prints_error(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {})

        cmd_sync(SimpleNamespace())

        output = capsys.readouterr().out
        assert "No Honcho config found" in output

    def test_sync_with_no_default_block_but_api_key_works(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {"apiKey": "key"})

        profiles = [FakeProfile("default"), FakeProfile("writer")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            cmd_sync(SimpleNamespace())

        cfg = _read_cfg(honcho_env["config_file"])
        assert "hermes.writer" in cfg["hosts"]


# ── cmd_peers ───────────────────────────────────────────────────────────────


class TestCmdPeers:
    def test_shows_all_profile_peers(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice", "aiPeer": "hermes"},
                "hermes.coder": {"peerName": "alice-code", "aiPeer": "hermes.coder"},
            },
        })

        profiles = [FakeProfile("default"), FakeProfile("coder")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles), \
             patch("honcho_integration.cli._active_profile_name", return_value="default"):
            cmd_peers(SimpleNamespace())

        output = capsys.readouterr().out
        assert "alice" in output
        assert "hermes.coder" in output
        assert "alice-code" in output

    def test_shows_not_set_for_missing_peers(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {}},
        })

        profiles = [FakeProfile("default")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles), \
             patch("honcho_integration.cli._active_profile_name", return_value="default"):
            cmd_peers(SimpleNamespace())

        output = capsys.readouterr().out
        assert "(not set)" in output


# ── --target-profile routing ────────────────────────────────────────────────


class TestTargetProfile:
    def test_target_profile_sets_override(self, honcho_env, monkeypatch):
        """--target-profile should route to the specified profile's host block."""
        import honcho_integration.cli as mod

        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"enabled": True},
                "hermes.coder": {"enabled": True, "aiPeer": "hermes.coder"},
            },
        })

        # Simulate: hermes honcho --target-profile coder disable
        args = SimpleNamespace(target_profile="coder", honcho_command="disable")

        honcho_command(args)

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.coder"]["enabled"] is False
        # Default should be untouched
        assert cfg["hosts"]["hermes"]["enabled"] is True

        # Clean up global state
        mod._profile_override = None

    def test_target_profile_enable_for_new_profile(self, honcho_env, monkeypatch):
        """Enable with --target-profile on a profile that has no block yet."""
        import honcho_integration.cli as mod

        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice", "memoryMode": "hybrid"},
            },
        })

        args = SimpleNamespace(target_profile="dreamer", honcho_command="enable")
        honcho_command(args)

        cfg = _read_cfg(honcho_env["config_file"])
        assert "hermes.dreamer" in cfg["hosts"]
        assert cfg["hosts"]["hermes.dreamer"]["enabled"] is True
        assert cfg["hosts"]["hermes.dreamer"]["aiPeer"] == "dreamer"

        mod._profile_override = None

    def test_target_profile_default_maps_to_base_host(self, honcho_env, monkeypatch):
        """--target-profile default should use 'hermes' as the host key."""
        import honcho_integration.cli as mod

        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": True}},
        })

        args = SimpleNamespace(target_profile="default", honcho_command="disable")
        honcho_command(args)

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes"]["enabled"] is False

        mod._profile_override = None


# ── clone_honcho_for_profile edge cases ─────────────────────────────────────


class TestCloneEdgeCases:
    def test_clone_calls_ensure_peer_exists(self, honcho_env, monkeypatch):
        """Cloning should eagerly create the peer."""
        calls = []
        monkeypatch.setattr(
            "honcho_integration.cli._ensure_peer_exists",
            lambda host_key=None: (calls.append(host_key), True)[1],
        )

        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"peerName": "alice"}},
        })

        clone_honcho_for_profile("coder")
        assert "hermes.coder" in calls

    def test_clone_shares_workspace_not_profile_derived(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"workspace": "team-workspace"}},
        })

        clone_honcho_for_profile("analyst")

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.analyst"]["workspace"] == "team-workspace"

    def test_clone_uses_hermes_as_default_workspace(self, honcho_env):
        """When no workspace is set anywhere, defaults to 'hermes'."""
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {}},
        })

        clone_honcho_for_profile("tester")

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.tester"]["workspace"] == "hermes"

    def test_clone_inherits_enabled_state(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": False, "peerName": "alice"}},
        })

        clone_honcho_for_profile("quiet")

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.quiet"]["enabled"] is False

    def test_clone_copies_dialectic_reasoning_level(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"dialecticReasoningLevel": "high"}},
        })

        clone_honcho_for_profile("thinker")

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.thinker"]["dialecticReasoningLevel"] == "high"

    def test_clone_does_not_copy_unknown_keys(self, honcho_env):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"customField": "should-not-copy", "peerName": "alice"}},
        })

        clone_honcho_for_profile("strict")

        cfg = _read_cfg(honcho_env["config_file"])
        assert "customField" not in cfg["hosts"]["hermes.strict"]
        assert cfg["hosts"]["hermes.strict"]["peerName"] == "alice"


# ── sync_honcho_profiles_quiet edge cases ───────────────────────────────────


class TestSyncQuietEdgeCases:
    def test_sync_quiet_no_profiles_module(self, honcho_env, monkeypatch):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {}},
        })
        with patch("hermes_cli.profiles.list_profiles", side_effect=ImportError):
            count = sync_honcho_profiles_quiet()
        assert count == 0

    def test_sync_quiet_no_api_key_no_default_block(self, honcho_env, monkeypatch):
        _write_cfg(honcho_env["config_file"], {"hosts": {}})
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)

        count = sync_honcho_profiles_quiet()
        assert count == 0

    def test_sync_quiet_with_env_api_key(self, honcho_env, monkeypatch):
        """Should sync even when apiKey is in env, not config."""
        _write_cfg(honcho_env["config_file"], {
            "hosts": {"hermes": {"peerName": "alice"}},
        })
        monkeypatch.setenv("HONCHO_API_KEY", "env-key")

        profiles = [FakeProfile("default"), FakeProfile("envprofile")]
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            count = sync_honcho_profiles_quiet()

        assert count == 1
        cfg = _read_cfg(honcho_env["config_file"])
        assert "hermes.envprofile" in cfg["hosts"]


# ── honcho_command routing ──────────────────────────────────────────────────


class TestHonchoCommandRouting:
    def test_routes_enable(self, honcho_env, monkeypatch, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": False, "aiPeer": "hermes"}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes")

        import honcho_integration.cli as mod
        args = SimpleNamespace(target_profile=None, honcho_command="enable")
        honcho_command(args)
        mod._profile_override = None

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes"]["enabled"] is True

    def test_routes_disable(self, honcho_env, monkeypatch, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"enabled": True}},
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes")

        import honcho_integration.cli as mod
        args = SimpleNamespace(target_profile=None, honcho_command="disable")
        honcho_command(args)
        mod._profile_override = None

        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes"]["enabled"] is False

    def test_routes_sync(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"peerName": "alice"}},
        })

        profiles = [FakeProfile("default"), FakeProfile("coder")]
        import honcho_integration.cli as mod
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles):
            args = SimpleNamespace(target_profile=None, honcho_command="sync")
            honcho_command(args)
        mod._profile_override = None

        cfg = _read_cfg(honcho_env["config_file"])
        assert "hermes.coder" in cfg["hosts"]

    def test_routes_peers(self, honcho_env, capsys):
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {"hermes": {"peerName": "alice"}},
        })

        profiles = [FakeProfile("default")]
        import honcho_integration.cli as mod
        with patch("hermes_cli.profiles.list_profiles", return_value=profiles), \
             patch("honcho_integration.cli._active_profile_name", return_value="default"):
            args = SimpleNamespace(target_profile=None, honcho_command="peers")
            honcho_command(args)
        mod._profile_override = None

        output = capsys.readouterr().out
        assert "alice" in output

    def test_unknown_command_prints_error(self, honcho_env, capsys):
        import honcho_integration.cli as mod
        args = SimpleNamespace(target_profile=None, honcho_command="foobar")
        honcho_command(args)
        mod._profile_override = None

        output = capsys.readouterr().out
        assert "Unknown honcho command" in output


# ── Integration: full enable→disable→enable cycle ──────────────────────────


# ── cmd_status with --target-profile ────────────────────────────────────────


class TestCmdStatusTargetProfile:
    """Verify cmd_status passes _host_key() to from_global_config so
    --target-profile actually shows the targeted profile's config."""

    def test_status_uses_host_key_for_config(self, honcho_env, monkeypatch, capsys):
        """from_global_config must receive the overridden host, not the
        default active host."""
        import honcho_integration.cli as mod

        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice", "aiPeer": "hermes", "enabled": True},
                "hermes.dreamer": {"peerName": "alice", "aiPeer": "dreamer", "enabled": True},
            },
        })

        # Track what host= value gets passed to from_global_config
        captured_hosts = []
        original_from_global = None

        from honcho_integration.client import HonchoClientConfig
        original_from_global = HonchoClientConfig.from_global_config

        def spy_from_global_config(**kwargs):
            captured_hosts.append(kwargs.get("host"))
            # Return a minimal config that won't trigger connection
            return HonchoClientConfig(
                host=kwargs.get("host", "hermes"),
                ai_peer=kwargs.get("host", "hermes"),
                enabled=False,  # skip connection attempt
            )

        monkeypatch.setattr(HonchoClientConfig, "from_global_config",
                            staticmethod(spy_from_global_config))

        # Simulate --target-profile dreamer
        mod._profile_override = "dreamer"
        try:
            cmd_status_args = SimpleNamespace(all=False)
            # Import honcho at module scope so the import check passes
            monkeypatch.setitem(__import__("sys").modules, "honcho", MagicMock())
            from honcho_integration.cli import cmd_status
            cmd_status(cmd_status_args)
        finally:
            mod._profile_override = None

        # The critical assertion: from_global_config was called with host="hermes.dreamer"
        assert "hermes.dreamer" in captured_hosts


# ── Integration: full enable→disable→enable cycle ──────────────────────────


class TestEnableDisableCycle:
    def test_full_cycle(self, honcho_env, monkeypatch, capsys):
        """Enable, disable, then re-enable a profile and verify state."""
        _write_cfg(honcho_env["config_file"], {
            "apiKey": "key",
            "hosts": {
                "hermes": {"peerName": "alice", "memoryMode": "hybrid"},
            },
        })
        monkeypatch.setattr("honcho_integration.cli._host_key", lambda: "hermes.tester")

        # Enable (should create block)
        cmd_enable(SimpleNamespace())
        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.tester"]["enabled"] is True
        assert cfg["hosts"]["hermes.tester"]["aiPeer"] == "tester"
        assert cfg["hosts"]["hermes.tester"]["memoryMode"] == "hybrid"

        # Disable
        cmd_disable(SimpleNamespace())
        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.tester"]["enabled"] is False

        # Re-enable (block already exists with aiPeer, should just flip)
        capsys.readouterr()  # clear
        cmd_enable(SimpleNamespace())
        cfg = _read_cfg(honcho_env["config_file"])
        assert cfg["hosts"]["hermes.tester"]["enabled"] is True
