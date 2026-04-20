"""Honcho audit log — structured, always-on, tail-friendly diagnostics.

Writes one line per event to ``$HERMES_HOME/logs/honcho-audit.log`` with
rotation at 5 MB × 3 files. Format::

    2026-04-20T14:12:03.482Z | event.name | session=abc turn=7 key=val ...

Separate from the main error log (logger name ``honcho.audit``, propagate=False)
so it never pollutes ``errors.log`` and is easy to tail on its own::

    tail -f ~/.hermes/logs/honcho-audit.log
    tail -f ~/.hermes/logs/honcho-audit.log | grep -E 'dialectic\\.'

Opt-out via ``memory.honcho.audit_log: false`` in config.yaml or the
``HONCHO_AUDIT_LOG=0`` env var. On by default (low volume — 1-3 lines/turn).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

_LOGGER_NAME = "honcho.audit"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3

_init_lock = threading.Lock()
_initialized = False
_enabled = True  # resolved at first use
_logger: logging.Logger | None = None


class _UTCFormatter(logging.Formatter):
    """ISO-8601 UTC timestamps with millisecond precision."""

    converter = time.gmtime

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = self.converter(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{t}.{int(record.msecs):03d}Z"


def _resolve_enabled() -> bool:
    """Audit log is on by default. Disabled by env var or config flag."""
    env = os.environ.get("HONCHO_AUDIT_LOG", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    # Config flag is checked lazily by callers that have a config handle;
    # a hard off from config is expressed by setting HONCHO_AUDIT_LOG=0
    # in the provider's _ensure_ready (see __init__.py).
    return True


def _init() -> None:
    """Create the rotating file handler once. Idempotent, thread-safe."""
    global _initialized, _enabled, _logger
    with _init_lock:
        if _initialized:
            return
        _enabled = _resolve_enabled()
        _logger = logging.getLogger(_LOGGER_NAME)
        # Don't bubble up to the root logger — keep audit separate from errors.log.
        _logger.propagate = False
        _logger.setLevel(logging.INFO if _enabled else logging.CRITICAL + 1)

        if _enabled and not _logger.handlers:
            try:
                log_dir = get_hermes_home() / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(
                    log_dir / "honcho-audit.log",
                    maxBytes=_MAX_BYTES,
                    backupCount=_BACKUP_COUNT,
                    encoding="utf-8",
                )
                handler.setFormatter(_UTCFormatter("%(asctime)s | %(message)s"))
                _logger.addHandler(handler)
            except Exception:
                # Audit must never break the plugin. Fall back to no-op.
                _enabled = False
                _logger.setLevel(logging.CRITICAL + 1)

        _initialized = True


def set_enabled(enabled: bool) -> None:
    """Force-enable/disable. Used by the provider when config says off."""
    global _enabled
    _init()
    _enabled = bool(enabled)
    if _logger is not None:
        _logger.setLevel(logging.INFO if _enabled else logging.CRITICAL + 1)


def is_enabled() -> bool:
    _init()
    return _enabled


def _fmt_value(v: Any) -> str:
    """Render a field value: quote strings with spaces, truncate long ones."""
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)
    s = str(v)
    # Longer cap for human-readable summary strings; most fields stay compact.
    _cap = 400
    if len(s) > _cap:
        s = s[: _cap - 3] + "..."
    # Replace whitespace so each event stays on one line + greppable.
    s = s.replace("\n", "\\n").replace("\t", " ")
    if " " in s or "|" in s or "=" in s:
        s = s.replace('"', '\\"')
        return f'"{s}"'
    return s


def log(event: str, **fields: Any) -> None:
    """Write one structured audit line. Safe to call from any thread.

    Example::

        audit.log("dialectic.return", pass_=0, ms=312, chars=0,
                  empty_reason="backend_empty")
    """
    _init()
    if not _enabled or _logger is None:
        return
    try:
        parts = [event]
        if fields:
            for k, v in fields.items():
                # Allow callers to use pass_ for the reserved word
                key = k.rstrip("_")
                parts.append(f"{key}={_fmt_value(v)}")
        _logger.info(" | ".join(parts))
    except Exception:
        # Audit must never break the plugin.
        pass


def log_path() -> Path:
    """Absolute path of the current audit log file."""
    return get_hermes_home() / "logs" / "honcho-audit.log"
