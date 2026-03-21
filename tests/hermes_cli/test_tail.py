import sys
from types import SimpleNamespace


class TestHermesTail:
    def test_tail_uses_latest_cli_session_when_no_session_arg(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        captured = {}

        class FakeDB:
            def search_sessions(self, source=None, limit=20, offset=0):
                captured["search_sessions"] = (source, limit, offset)
                return [{"id": "sess-123", "source": "cli", "title": "Demo session", "message_count": 42}]

            def get_session(self, session_id):
                captured["get_session"] = session_id
                return {"id": session_id, "source": "cli", "title": "Demo session", "message_count": 42}

            def get_recent_messages(self, session_id, limit=20):
                captured.setdefault("get_recent_messages", []).append((session_id, limit))
                return [
                    {"id": 11, "role": "user", "content": "hello there", "timestamp": 1700000000.0},
                    {"id": 12, "role": "assistant", "content": "hi back", "timestamp": 1700000001.0},
                ]

            def get_messages_since(self, session_id, after_id=0, limit=20):
                captured.setdefault("get_messages_since", []).append((session_id, after_id, limit))
                return []

            def close(self):
                captured["closed"] = True

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session=None, limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert captured["search_sessions"] == ("cli", 1, 0)
        assert captured["get_session"] == "sess-123"
        assert captured["get_recent_messages"] == [("sess-123", 20)]
        assert "get_messages_since" not in captured
        assert "Hermes tail" in output
        assert "session:  sess-123" in output
        assert "source:   cli" in output
        assert "title:    Demo session" in output
        assert "messages: 42" in output
        assert "showing last 2 message(s)" in output
        assert "hello there" in output
        assert "hi back" in output
        assert captured["closed"] is True

    def test_tail_uses_requested_source_for_latest_session_lookup(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        captured = {}

        class FakeDB:
            def search_sessions(self, source=None, limit=20, offset=0):
                captured["search_sessions"] = (source, limit, offset)
                return [{"id": "tg-001", "source": "telegram", "title": "Gateway Chat", "message_count": 3}]

            def get_session(self, session_id):
                return {"id": session_id, "source": "telegram", "title": "Gateway Chat", "message_count": 3}

            def get_recent_messages(self, session_id, limit=20):
                return [{"id": 21, "role": "assistant", "content": "hello from telegram", "timestamp": 1700000100.0}]

            def close(self):
                captured["closed"] = True

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session=None, source="telegram", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert captured["search_sessions"] == ("telegram", 1, 0)
        assert "source:   telegram" in output
        assert "hello from telegram" in output
        assert captured["closed"] is True

    def test_tail_resolves_session_title_when_id_lookup_fails(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        class FakeDB:
            def resolve_session_id(self, value):
                assert value == "Project Alpha"
                return None

            def resolve_session_by_title(self, value):
                assert value == "Project Alpha"
                return "sess-title"

            def get_session(self, session_id):
                assert session_id == "sess-title"
                return {"id": session_id, "source": "cli", "title": "Project Alpha", "message_count": 1}

            def get_recent_messages(self, session_id, limit=20):
                return [
                    {
                        "id": 3,
                        "role": "tool",
                        "tool_name": "terminal",
                        "content": '{"exit_code":0,"output":"done","success":true}',
                        "timestamp": 1700000002.0,
                    },
                ]

            def get_messages_since(self, session_id, after_id=0, limit=20):
                return []

            def close(self):
                pass

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session="Project Alpha", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert "Project Alpha" in output
        assert "tool:terminal" in output
        assert "exit=0" in output
        assert "done" in output

    def test_tail_follow_prints_new_messages_until_interrupted(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        calls = []

        class FakeDB:
            def resolve_session_id(self, value):
                return "sess-follow"

            def get_session(self, session_id):
                return {"id": session_id, "source": "cli", "title": None, "message_count": 2}

            def get_recent_messages(self, session_id, limit=20):
                return [{"id": 5, "role": "assistant", "content": "first chunk", "timestamp": 1700000003.0}]

            def get_messages_since(self, session_id, after_id=0, limit=20):
                calls.append((session_id, after_id, limit))
                if len(calls) == 1:
                    return [{"id": 6, "role": "assistant", "content": "second chunk", "timestamp": 1700000004.0}]
                return []

            def close(self):
                pass

        def fake_sleep(_seconds):
            if len(calls) >= 1:
                raise KeyboardInterrupt()

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())
        monkeypatch.setattr(tail_mod.time, "sleep", fake_sleep)

        tail_mod.tail_command(SimpleNamespace(session="sess-follow", limit=20, follow=True, poll_interval=0.1))

        output = capsys.readouterr().out
        assert calls == [
            ("sess-follow", 5, 20),
        ]
        assert "following for new messages" in output
        assert "Ctrl-C to stop" in output
        assert "first chunk" in output
        assert "second chunk" in output
        assert "stopped tailing" in output.lower()

    def test_tail_reports_missing_session(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        class FakeDB:
            def resolve_session_id(self, value):
                return None

            def resolve_session_by_title(self, value):
                return None

            def close(self):
                pass

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session="missing", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert "Session 'missing' not found." in output

    def test_tail_reports_missing_source_sessions_cleanly(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        class FakeDB:
            def search_sessions(self, source=None, limit=20, offset=0):
                assert source == "signal"
                return []

            def close(self):
                pass

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session=None, source="signal", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert "No signal sessions found." in output

    def test_tail_supports_all_sources_for_latest_lookup(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        captured = {}

        class FakeDB:
            def search_sessions(self, source=None, limit=20, offset=0):
                captured["search_sessions"] = (source, limit, offset)
                return [{"id": "mixed-1", "source": "discord", "title": "Server Room", "message_count": 2}]

            def get_session(self, session_id):
                return {"id": session_id, "source": "discord", "title": "Server Room", "message_count": 2}

            def get_recent_messages(self, session_id, limit=20):
                return [{"id": 31, "role": "assistant", "content": "latest from anywhere", "timestamp": 1700000200.0}]

            def close(self):
                pass

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session=None, source="all", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert captured["search_sessions"] == (None, 1, 0)
        assert "source:   discord" in output
        assert "latest from anywhere" in output

    def test_tail_reports_empty_session_cleanly(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        class FakeDB:
            def resolve_session_id(self, value):
                return "sess-empty"

            def get_session(self, session_id):
                return {"id": session_id, "source": "cli", "title": "Quiet Session", "message_count": 0}

            def get_recent_messages(self, session_id, limit=20):
                return []

            def close(self):
                pass

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())

        tail_mod.tail_command(SimpleNamespace(session="sess-empty", limit=20, follow=False, poll_interval=0.1))

        output = capsys.readouterr().out
        assert "Quiet Session" in output
        assert "no messages yet" in output

    def test_tail_follow_waits_for_messages_in_empty_session(self, monkeypatch, capsys):
        from hermes_cli import tail as tail_mod

        calls = []

        class FakeDB:
            def resolve_session_id(self, value):
                return "sess-wait"

            def get_session(self, session_id):
                return {"id": session_id, "source": "cli", "title": "Waiting Room", "message_count": 0}

            def get_recent_messages(self, session_id, limit=20):
                return []

            def get_messages_since(self, session_id, after_id=0, limit=20):
                calls.append((session_id, after_id, limit))
                if len(calls) == 1:
                    return [{"id": 41, "role": "assistant", "content": "first arrival", "timestamp": 1700000300.0}]
                return []

            def close(self):
                pass

        def fake_sleep(_seconds):
            if len(calls) >= 1:
                raise KeyboardInterrupt()

        monkeypatch.setattr(tail_mod, "SessionDB", lambda: FakeDB())
        monkeypatch.setattr(tail_mod.time, "sleep", fake_sleep)

        tail_mod.tail_command(SimpleNamespace(session="sess-wait", limit=20, follow=True, poll_interval=0.1))

        output = capsys.readouterr().out
        assert "Waiting Room" in output
        assert "no messages yet" in output
        assert "waiting for first message" in output
        assert "first arrival" in output


def test_main_routes_tail_command(monkeypatch):
    import hermes_cli.main as main_mod

    captured = {}

    def fake_tail_command(args):
        captured["session"] = args.session
        captured["source"] = args.source
        captured["limit"] = args.limit
        captured["follow"] = args.follow

    monkeypatch.setattr("hermes_cli.tail.tail_command", fake_tail_command)
    monkeypatch.setattr(sys, "argv", ["hermes", "tail", "sess-xyz", "--source", "telegram", "--limit", "5", "--follow"])

    main_mod.main()

    assert captured == {"session": "sess-xyz", "source": "telegram", "limit": 5, "follow": True}
