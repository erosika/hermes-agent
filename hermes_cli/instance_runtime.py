"""Hermes named instance runtime helpers.

Keeps instance resolution independent from the rest of the CLI bootstrap so we can
set HERMES_HOME before dotenv/config-heavy modules import.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_INSTANCE_NAME = "main"
_DEFAULT_HOME_NAME = ".hermes"
_INSTANCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_INSTANCE_FLAGS = ("--instance",)


@dataclass(frozen=True)
class InstanceRuntime:
    instance: str
    base_home: Path
    home: Path
    honcho_host: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_instance_name(name: str | None) -> str:
    raw = (name or "").strip().lower()
    if not raw:
        return DEFAULT_INSTANCE_NAME
    if raw in {DEFAULT_INSTANCE_NAME, "default"}:
        return DEFAULT_INSTANCE_NAME
    if not _INSTANCE_RE.fullmatch(raw):
        raise ValueError(
            "Invalid instance name. Use lowercase letters, numbers, underscores, or hyphens."
        )
    return raw


def _infer_instance_from_home(home: Path) -> str:
    if home.parent.name == "instances" and home.name:
        try:
            return normalize_instance_name(home.name)
        except ValueError:
            return DEFAULT_INSTANCE_NAME
    return DEFAULT_INSTANCE_NAME


def _derive_base_from_home(home: Path) -> Path:
    if home.parent.name == "instances":
        return home.parent.parent
    return home


def get_base_hermes_home() -> Path:
    base = os.getenv("HERMES_BASE_HOME", "").strip()
    if base:
        return Path(base).expanduser()

    home_env = os.getenv("HERMES_HOME", "").strip()
    if home_env:
        return _derive_base_from_home(Path(home_env).expanduser())

    return Path.home() / _DEFAULT_HOME_NAME


def get_active_instance_name() -> str:
    explicit = os.getenv("HERMES_INSTANCE", "").strip()
    if explicit:
        return normalize_instance_name(explicit)

    home_env = os.getenv("HERMES_HOME", "").strip()
    if home_env:
        return _infer_instance_from_home(Path(home_env).expanduser())

    return DEFAULT_INSTANCE_NAME


def get_instance_home(instance_name: str | None = None, *, base_home: Path | None = None) -> Path:
    instance = normalize_instance_name(instance_name or get_active_instance_name())
    root = Path(base_home) if base_home is not None else get_base_hermes_home()
    if instance == DEFAULT_INSTANCE_NAME:
        return root
    return root / "instances" / instance


def resolve_honcho_host(instance_name: str | None = None) -> str:
    instance = normalize_instance_name(instance_name or get_active_instance_name())
    if instance == DEFAULT_INSTANCE_NAME:
        return "hermes"
    return f"hermes.{instance}"


def get_active_honcho_host() -> str:
    explicit = os.getenv("HERMES_HONCHO_HOST", "").strip()
    if explicit:
        return explicit
    return resolve_honcho_host(get_active_instance_name())


def get_instance_registry_path(base_home: Path | None = None) -> Path:
    root = Path(base_home) if base_home is not None else get_base_hermes_home()
    return root / "instances.json"


def build_instance_runtime(instance_name: str | None = None, *, base_home: Path | None = None) -> InstanceRuntime:
    instance = normalize_instance_name(instance_name or get_active_instance_name())
    root = Path(base_home) if base_home is not None else get_base_hermes_home()
    home = get_instance_home(instance, base_home=root)
    return InstanceRuntime(
        instance=instance,
        base_home=root,
        home=home,
        honcho_host=resolve_honcho_host(instance),
    )


def register_instance(runtime: InstanceRuntime) -> None:
    registry_path = get_instance_registry_path(runtime.base_home)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {"instances": {}}
    if registry_path.exists():
        try:
            existing = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except Exception:
            pass

    instances = payload.setdefault("instances", {})
    if not isinstance(instances, dict):
        instances = {}
        payload["instances"] = instances

    instances[runtime.instance] = {
        "home": str(runtime.home),
        "honcho_host": runtime.honcho_host,
        "last_used_at": _utc_now_iso(),
    }

    registry_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _extract_instance_from_argv(argv: Iterable[str]) -> tuple[list[str], str | None]:
    cleaned: list[str] = []
    selected: str | None = None
    items = list(argv)
    i = 0
    while i < len(items):
        arg = items[i]
        if any(arg.startswith(f"{flag}=") for flag in _INSTANCE_FLAGS):
            _, _, value = arg.partition("=")
            if not value.strip():
                raise ValueError(f"{arg.split('=')[0]} requires a value")
            selected = value.strip()
            i += 1
            continue
        if arg in _INSTANCE_FLAGS:
            if i + 1 >= len(items):
                raise ValueError(f"{arg} requires a value")
            value = items[i + 1].strip()
            if not value:
                raise ValueError(f"{arg} requires a value")
            selected = value
            i += 2
            continue
        cleaned.append(arg)
        i += 1
    return cleaned, selected


def bootstrap_instance_env(argv: Iterable[str]) -> list[str]:
    """Resolve the active Hermes instance and export runtime env vars.

    Returns argv with instance-selection flags removed so argparse does not need to
    know where `--instance` or `--name` appeared.
    """

    cleaned, selected = _extract_instance_from_argv(argv)

    existing_base = os.getenv("HERMES_BASE_HOME", "").strip()
    current_home = os.getenv("HERMES_HOME", "").strip()

    if selected:
        current_instance = selected
    elif existing_base:
        current_instance = os.getenv("HERMES_INSTANCE") or DEFAULT_INSTANCE_NAME
    elif current_home:
        current_instance = _infer_instance_from_home(Path(current_home).expanduser())
    else:
        current_instance = os.getenv("HERMES_INSTANCE") or DEFAULT_INSTANCE_NAME

    if existing_base:
        base_home = Path(existing_base).expanduser()
    elif current_home:
        base_home = _derive_base_from_home(Path(current_home).expanduser())
    else:
        base_home = Path.home() / _DEFAULT_HOME_NAME

    runtime = build_instance_runtime(current_instance, base_home=base_home)
    os.environ["HERMES_INSTANCE"] = runtime.instance
    os.environ["HERMES_BASE_HOME"] = str(runtime.base_home)
    os.environ["HERMES_HOME"] = str(runtime.home)
    os.environ["HERMES_HONCHO_HOST"] = runtime.honcho_host

    register_instance(runtime)
    return cleaned
