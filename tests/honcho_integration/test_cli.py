"""Tests for Honcho CLI helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from honcho_integration.cli import (
    _resolve_api_key,
    _resolve_base_url,
    _has_honcho_credentials,
    cmd_identity,
    cmd_setup,
    cmd_status,
)
from honcho_integration.client import HonchoClientConfig


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


class TestResolveBaseUrl:
    def test_prefers_host_scoped_snake_case_value(self):
        cfg = {
            "baseUrl": "http://root:8000",
            "hosts": {"hermes": {"base_url": "http://host:8000"}},
        }
        assert _resolve_base_url(cfg) == "http://host:8000"

    def test_prefers_canonical_baseUrl_within_same_scope(self):
        cfg = {
            "base_url": "http://root-snake:8000",
            "baseUrl": "http://root-camel:8000",
        }
        assert _resolve_base_url(cfg) == "http://root-camel:8000"

    def test_accepts_root_level_aliases(self):
        assert _resolve_base_url({"baseURL": "http://root:8001"}) == "http://root:8001"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://env:8000")
        assert _resolve_base_url({}) == "http://env:8000"
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)


class TestHasHonchoCredentials:
    def test_true_with_api_key(self):
        assert _has_honcho_credentials({"apiKey": "secret"}) is True

    def test_true_with_base_url_only(self):
        assert _has_honcho_credentials({"base_url": "http://local:8000"}) is True

    def test_false_without_key_or_base_url(self, monkeypatch):
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        assert _has_honcho_credentials({}) is False


class TestHonchoCliCommands:
    def test_identity_allows_base_url_only_config(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000"}}}
        manager = MagicMock()
        manager.get_or_create.return_value = object()

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr(
            "honcho_integration.client.HonchoClientConfig.from_global_config",
            lambda: HonchoClientConfig(base_url="http://localhost:8000", enabled=True),
        )
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", lambda hcfg: MagicMock())
        monkeypatch.setattr("honcho_integration.session.HonchoSessionManager", lambda honcho, config: manager)

        cmd_identity(SimpleNamespace(file=None, show=False))
        out = capsys.readouterr().out

        assert "No API key configured" not in out
        manager.get_or_create.assert_called_once()

    def test_setup_allows_existing_base_url_without_api_key(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000"}}}
        prompts = iter(["", "http://localhost:8000", "eri", "hermes", "hybrid", "async", "hybrid", "per-session"])

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr("honcho_integration.cli._write_config", lambda updated: None)
        monkeypatch.setattr("honcho_integration.cli._ensure_sdk_installed", lambda: True)
        monkeypatch.setattr("honcho_integration.cli._prompt", lambda *args, **kwargs: next(prompts))
        monkeypatch.setattr("honcho_integration.client.reset_honcho_client", lambda: None)
        monkeypatch.setattr(
            "honcho_integration.client.HonchoClientConfig.from_global_config",
            lambda: HonchoClientConfig(base_url="http://localhost:8000", enabled=True, peer_name="eri"),
        )
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", lambda hcfg: MagicMock())

        cmd_setup(SimpleNamespace())
        out = capsys.readouterr().out

        assert "No API key configured" not in out
        assert "Honcho is ready" in out

    def test_status_treats_base_url_only_as_connectable(self, monkeypatch, capsys):
        cfg = {"hosts": {"hermes": {"base_url": "http://localhost:8000", "enabled": True}}}
        hcfg = HonchoClientConfig(base_url="http://localhost:8000", enabled=True)
        get_client = MagicMock(return_value=MagicMock())

        monkeypatch.setattr("honcho_integration.cli._read_config", lambda: cfg)
        monkeypatch.setattr("honcho_integration.client.HonchoClientConfig.from_global_config", lambda: hcfg)
        monkeypatch.setattr("honcho_integration.client.get_honcho_client", get_client)
        monkeypatch.setitem(__import__("sys").modules, "honcho", MagicMock())

        cmd_status(SimpleNamespace())
        out = capsys.readouterr().out

        assert "Base URL:" in out
        assert "Connection... OK" in out
        get_client.assert_called_once_with(hcfg)

