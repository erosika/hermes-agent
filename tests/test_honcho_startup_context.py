from types import SimpleNamespace

from run_agent import AIAgent


class TestHonchoStartupContext:
    def test_pop_startup_snapshot_formats_and_consumes_once(self):
        agent = object.__new__(AIAgent)
        agent._honcho_config = SimpleNamespace(
            tools_startup_context=True,
            peer_name="alice",
        )
        agent._honcho_startup_snapshot = {
            "alice": {
                "representation": "Knows the user well.",
                "card": "- prefers directness",
            }
        }

        first = agent._pop_startup_snapshot()
        second = agent._pop_startup_snapshot()

        assert "# Honcho Memory (startup context)" in first
        assert "## User representation\nKnows the user well." in first
        assert "- prefers directness" in first
        assert second == ""

    def test_pop_startup_snapshot_returns_empty_when_feature_disabled(self):
        agent = object.__new__(AIAgent)
        agent._honcho_config = SimpleNamespace(
            tools_startup_context=False,
            peer_name="alice",
        )
        agent._honcho_startup_snapshot = {
            "alice": {"representation": "Knows the user well.", "card": "- prefers directness"}
        }

        assert agent._pop_startup_snapshot() == ""
        assert agent._honcho_startup_snapshot == {
            "alice": {"representation": "Knows the user well.", "card": "- prefers directness"}
        }
