"""Saving provider settings must not convert a stored explicit null into key-absence.

contextTokens: null means uncapped; an absent key means the default cap.
The web form renders a stored null as a blank input, so a save of any
unrelated field used to pop the key and silently re-enable the cap.
"""

from hermes_cli import web_server
from plugins.memory.config_schema import get_provider_config_schema


def test_blank_save_preserves_stored_explicit_null():
    provider = get_provider_config_schema("honcho")
    target = {"contextTokens": None, "dialecticMaxChars": 600}

    web_server._apply_field_values(
        provider,
        {"contextTokens": "", "dialecticMaxChars": "800"},
        lambda field: target,
    )

    assert "contextTokens" in target
    assert target["contextTokens"] is None
    assert target["dialecticMaxChars"] == 800


def test_blank_save_still_pops_non_null_values():
    provider = get_provider_config_schema("honcho")
    target = {"contextTokens": 1200}

    web_server._apply_field_values(
        provider,
        {"contextTokens": ""},
        lambda field: target,
    )

    assert "contextTokens" not in target
