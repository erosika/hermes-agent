"""Tests for Honcho cron session write guard (#4052).

Cron sessions must not write messages to Honcho — the cron prompt
contains system instructions ("You are Hermes...") that would be
misattributed to the user peer, corrupting the user representation.

Verifies that:
1. _honcho_sync() is a no-op when platform == "cron"
2. _honcho_save_user_observation() rejects writes when platform == "cron"
3. Non-cron sessions still sync normally
"""

import json
import types
import sys
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch):
    """Stub heavy dependencies so run_agent can import without side effects."""
    for mod_name in (
        "dotenv",
        "yaml",
        "rich",
        "rich.console",
        "rich.panel",
        "rich.markdown",
        "rich.syntax",
        "rich.live",
        "rich.text",
        "rich.table",
        "rich.box",
        "rich.theme",
    ):
        if mod_name not in sys.modules:
            monkeypatch.setitem(sys.modules, mod_name, types.ModuleType(mod_name))

    fake_dotenv = sys.modules["dotenv"]
    fake_dotenv.load_dotenv = lambda *a, **kw: None


def _make_agent(platform: str = "cron"):
    """Create a minimal AIAgent-like object with Honcho state wired up."""
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.platform = platform
    agent.quiet_mode = True

    # Mock Honcho session manager
    agent._honcho = MagicMock()
    agent._honcho_session_key = "test-session"

    mock_session = MagicMock()
    mock_session.messages = []
    agent._honcho.get_or_create.return_value = mock_session

    return agent, mock_session


class TestHonchoSyncCronGuard:
    """_honcho_sync must skip writes for cron sessions."""

    def test_cron_session_skips_sync(self):
        agent, mock_session = _make_agent(platform="cron")
        agent._honcho_sync("You are Hermes, an AI assistant...", "Sure, here's the result.")

        # Should never touch the session
        agent._honcho.get_or_create.assert_not_called()
        mock_session.add_message.assert_not_called()
        agent._honcho.save.assert_not_called()

    def test_non_cron_session_syncs_normally(self):
        agent, mock_session = _make_agent(platform="telegram")
        agent._honcho_sync("Hello!", "Hi there!")

        agent._honcho.get_or_create.assert_called_once_with("test-session")
        assert mock_session.add_message.call_count == 2
        mock_session.add_message.assert_any_call("user", "Hello!")
        mock_session.add_message.assert_any_call("assistant", "Hi there!")
        agent._honcho.save.assert_called_once()

    def test_cli_session_syncs_normally(self):
        agent, mock_session = _make_agent(platform="cli")
        agent._honcho_sync("What's the weather?", "I don't have weather tools.")

        agent._honcho.get_or_create.assert_called_once()
        assert mock_session.add_message.call_count == 2

    def test_none_platform_syncs_normally(self):
        """Platform=None (e.g. direct AIAgent usage) should still sync."""
        agent, mock_session = _make_agent(platform=None)
        agent._honcho_sync("test", "response")

        agent._honcho.get_or_create.assert_called_once()


class TestHonchoObservationCronGuard:
    """_honcho_save_user_observation must reject writes for cron sessions."""

    def test_cron_session_rejects_observation(self):
        agent, mock_session = _make_agent(platform="cron")
        result = json.loads(agent._honcho_save_user_observation("User prefers dark mode"))

        assert result["success"] is False
        assert "cron" in result["error"].lower()
        agent._honcho.get_or_create.assert_not_called()

    def test_non_cron_session_saves_observation(self):
        agent, mock_session = _make_agent(platform="telegram")
        result = json.loads(agent._honcho_save_user_observation("User prefers dark mode"))

        assert result["success"] is True
        agent._honcho.get_or_create.assert_called_once()
        mock_session.add_message.assert_called_once()
        # Verify the observation prefix is present
        call_args = mock_session.add_message.call_args
        assert call_args[0][0] == "user"
        assert "[observation]" in call_args[0][1]
