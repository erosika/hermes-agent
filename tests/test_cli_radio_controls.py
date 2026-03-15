import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import cli as cli_mod
from cli import HermesCLI
from prompt_toolkit.keys import Keys


class _FakeBuffer:
    def __init__(self, text=""):
        self.text = text


class _FakeApp:
    def __init__(self, text=""):
        self.current_buffer = _FakeBuffer(text)

    def invalidate(self):
        pass


def _make_cli_stub(buffer_text="", *, agent_running=False):
    cli = HermesCLI.__new__(HermesCLI)
    cli._app = _FakeApp(buffer_text)
    cli._radio_menu_state = None
    cli._clarify_state = None
    cli._approval_state = None
    cli._sudo_state = None
    cli._secret_state = None
    cli._agent_running = agent_running
    return cli


class _FakeRadio:
    def __init__(self):
        self.calls = []

    async def toggle_pause(self):
        self.calls.append("pause")
        return "Paused"

    async def skip(self):
        self.calls.append("skip")
        return "Skipping..."

    async def adjust_volume(self, delta):
        self.calls.append(("volume", delta))
        return f"Volume delta {delta}"

    async def toggle_mute(self):
        self.calls.append("mute")
        return "Muted"


def test_radio_transport_shortcuts_stay_available_while_agent_is_working():
    cli = _make_cli_stub(agent_running=True)

    with patch("radio.player.HermesRadio.active", return_value=True):
        assert cli._can_use_radio_transport_shortcuts() is True


def test_radio_transport_shortcuts_block_when_user_is_typing():
    cli = _make_cli_stub(buffer_text="next song plz", agent_running=True)

    with patch("radio.player.HermesRadio.active", return_value=True):
        assert cli._can_use_radio_transport_shortcuts() is False


def test_run_radio_shortcut_action_dispatches_skip_pause_volume_and_mute():
    cli = _make_cli_stub(agent_running=True)
    radio = _FakeRadio()

    with patch("radio.player.HermesRadio.active", return_value=True), \
         patch("radio.player.HermesRadio.get", return_value=radio), \
         patch("tools.radio_tool._run_radio_async", side_effect=lambda coro: asyncio.run(coro)):
        assert cli._run_radio_shortcut_action("pause") == "Paused"
        assert cli._run_radio_shortcut_action("skip") == "Skipping..."
        assert cli._run_radio_shortcut_action("volume_up") == "Volume delta 5"
        assert cli._run_radio_shortcut_action("volume_down") == "Volume delta -5"
        assert cli._run_radio_shortcut_action("mute") == "Muted"

    assert radio.calls == ["pause", "skip", ("volume", 5), ("volume", -5), "mute"]


class _FakeThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


class _CaptureApplication:
    def __init__(self, *args, **kwargs):
        self.key_bindings = kwargs["key_bindings"]
        self.is_running = False

    def run(self):
        return None

    def invalidate(self):
        pass

    def exit(self):
        pass


def test_escape_exits_radio_control_mode():
    shell = HermesCLI(compact=True, max_turns=1)
    shell.show_banner = lambda: None
    shell._print_exit_summary = lambda: None

    with patch.object(cli_mod, "Application", _CaptureApplication), \
         patch.object(cli_mod, "patch_stdout", lambda *args, **kwargs: nullcontext()), \
         patch.object(cli_mod.threading, "Thread", _FakeThread), \
         patch.object(cli_mod.atexit, "register", lambda *args, **kwargs: None):
        shell.run()

    shell._radio_control_mode = True
    bindings = shell._app.key_bindings.get_bindings_for_keys((Keys.Escape,))

    for binding in bindings:
        if binding.filter():
            binding.handler(SimpleNamespace(app=_FakeApp()))

    assert shell._radio_control_mode is False
