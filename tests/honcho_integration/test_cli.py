"""Tests for Honcho CLI helpers."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from honcho_integration import cli as honcho_cli
from honcho_integration.cli import _effective_value, _resolve_api_key


class TestResolveApiKey:
    def test_prefers_host_scoped_key(self):
        cfg = {
            "apiKey": "root-key",
            "hosts": {
                "hermes": {
                    "apiKey": "host-key",
                }
            },
        }
        assert _resolve_api_key(cfg) == "host-key"

    def test_falls_back_to_root_key(self):
        cfg = {
            "apiKey": "root-key",
            "hosts": {"hermes": {}},
        }
        assert _resolve_api_key(cfg) == "root-key"

    def test_falls_back_to_env_key(self, monkeypatch):
        monkeypatch.setenv("HONCHO_API_KEY", "env-key")
        assert _resolve_api_key({}) == "env-key"
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)


class TestEffectiveValue:
    def test_prefers_explicit_false_in_host_block(self):
        cfg = {
            "toolsStartupContext": True,
            "hosts": {
                "hermes": {
                    "toolsStartupContext": False,
                }
            },
        }

        assert _effective_value(cfg, "toolsStartupContext", default=None) is False


class TestHonchoCliWrites:
    def test_cmd_setup_writes_host_scoped_values_and_keeps_root_defaults(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({
            "apiKey": "root-key",
            "memoryMode": "honcho",
            "recallMode": "context",
            "toolsStartupContext": False,
            "sessionStrategy": "global",
            "hosts": {
                "hermes": {
                    "peerName": "old-user",
                }
            },
        }))
        monkeypatch.setattr(honcho_cli, "GLOBAL_CONFIG_PATH", cfg_path)
        monkeypatch.setattr(honcho_cli, "_config_path", lambda: cfg_path)
        monkeypatch.setattr(honcho_cli, "_ensure_sdk_installed", lambda: True)

        prompts = iter([
            "",          # keep root api key
            "eri",       # peer name
            "hermes-ws", # workspace
            "hybrid",    # memory mode
            "turn",      # write frequency
            "tools",     # recall mode
            "y",         # startup context
            "per-repo",  # session strategy
        ])
        monkeypatch.setattr(honcho_cli, "_prompt", lambda *a, **k: next(prompts))
        monkeypatch.setattr(honcho_cli, "_write_config", lambda cfg: cfg_path.write_text(json.dumps(cfg, indent=2)))
        monkeypatch.setattr(honcho_cli, "_read_config", lambda: json.loads(cfg_path.read_text()))

        fake_hcfg = SimpleNamespace(
            workspace_id="hermes-ws",
            peer_name="eri",
            memory_mode="hybrid",
            peer_memory_modes={},
            write_frequency="turn",
            recall_mode="tools",
            tools_startup_context=True,
            resolve_session_name=lambda: "session-name",
        )
        monkeypatch.setattr("honcho_integration.client.reset_honcho_client", lambda: None)
        monkeypatch.setattr("honcho_integration.client.HonchoClientConfig.from_global_config", lambda: fake_hcfg)
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", lambda cfg: MagicMock())

        honcho_cli.cmd_setup(SimpleNamespace())

        saved = json.loads(cfg_path.read_text())
        assert saved["apiKey"] == "root-key"
        assert saved["memoryMode"] == "honcho"
        assert saved["recallMode"] == "context"
        assert saved["toolsStartupContext"] is False
        assert saved["sessionStrategy"] == "global"

        hermes = saved["hosts"]["hermes"]
        assert hermes["peerName"] == "eri"
        assert hermes["workspace"] == "hermes-ws"
        assert hermes["memoryMode"] == "hybrid"
        assert hermes["writeFrequency"] == "turn"
        assert hermes["recallMode"] == "tools"
        assert hermes["toolsStartupContext"] is True
        assert hermes["sessionStrategy"] == "per-repo"
        assert hermes["aiPeer"] == "hermes"

    def test_cmd_mode_writes_host_override_without_touching_root_default(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({
            "memoryMode": "honcho",
            "hosts": {"hermes": {}},
        }))
        monkeypatch.setattr(honcho_cli, "GLOBAL_CONFIG_PATH", cfg_path)
        monkeypatch.setattr(honcho_cli, "_config_path", lambda: cfg_path)

        honcho_cli.cmd_mode(SimpleNamespace(mode="hybrid"))

        saved = json.loads(cfg_path.read_text())
        assert saved["memoryMode"] == "honcho"
        assert saved["hosts"]["hermes"]["memoryMode"] == "hybrid"

    def test_cmd_tokens_writes_host_override_without_touching_root_default(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({
            "contextTokens": 321,
            "dialecticMaxChars": 456,
            "hosts": {"hermes": {}},
        }))
        monkeypatch.setattr(honcho_cli, "GLOBAL_CONFIG_PATH", cfg_path)
        monkeypatch.setattr(honcho_cli, "_config_path", lambda: cfg_path)

        honcho_cli.cmd_tokens(SimpleNamespace(context=800, dialectic=600))

        saved = json.loads(cfg_path.read_text())
        assert saved["contextTokens"] == 321
        assert saved["dialecticMaxChars"] == 456
        assert saved["hosts"]["hermes"]["contextTokens"] == 800
        assert saved["hosts"]["hermes"]["dialecticMaxChars"] == 600

