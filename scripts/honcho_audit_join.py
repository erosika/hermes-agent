#!/usr/bin/env python3
"""honcho_audit_join.py — cross-reference Hermes audit log with Honcho backend.

Reads ``$HERMES_HOME/logs/honcho-audit.log`` and for each ``dialectic.return``
event pulls the matching tail of messages from the Honcho backend (same
workspace + session) within a small timestamp window. Prints a turn-by-turn
table: what Hermes fired, how long it took, what came back, and what the
backend session actually contains around that time.

Usage:
    python scripts/honcho_audit_join.py                  # last 20 dialectic events
    python scripts/honcho_audit_join.py --tail 50        # last 50
    python scripts/honcho_audit_join.py --empty-only     # only empty returns
    python scripts/honcho_audit_join.py --since 10m      # events in the last 10 minutes
    python scripts/honcho_audit_join.py --session hermes-agent
    python scripts/honcho_audit_join.py --no-backend     # skip Honcho API fetches

Honest limits:
- Timestamp correlation is fuzzy (client monotonic vs server wall-clock).
- Only works when HERMES_HOME is the current profile; reads the active honcho
  config via the Hermes plugin's own loader.
- No polling — one-shot. Run it after a session, or pipe to ``watch``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Resolve HERMES_HOME the same way Hermes does.
HERMES_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERMES_ROOT))

from hermes_constants import get_hermes_home  # noqa: E402

AUDIT_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s*\|\s*(?P<event>[\w.]+)\s*(?:\|\s*(?P<fields>.*))?$"
)
FIELD_RE = re.compile(r"(\w+)=(?:\"([^\"]*)\"|(\S+))")


def parse_line(line: str) -> dict[str, Any] | None:
    m = AUDIT_LINE_RE.match(line.rstrip())
    if not m:
        return None
    ts = datetime.strptime(m["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    event = m["event"]
    fields: dict[str, Any] = {}
    if m["fields"]:
        for fm in FIELD_RE.finditer(m["fields"]):
            k = fm.group(1)
            v = fm.group(2) if fm.group(2) is not None else fm.group(3)
            if v is not None:
                if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                    fields[k] = int(v)
                elif v in ("true", "false"):
                    fields[k] = v == "true"
                else:
                    fields[k] = v
    return {"ts": ts, "event": event, **fields}


def read_audit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"[audit log not found: {path}]", file=sys.stderr)
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            ev = parse_line(line)
            if ev:
                out.append(ev)
    return out


def parse_since(s: str) -> timedelta:
    """'10m', '2h', '1d', or '300s'."""
    m = re.match(r"^(\d+)([smhd])$", s)
    if not m:
        raise argparse.ArgumentTypeError(f"bad --since: {s}")
    n, unit = int(m.group(1)), m.group(2)
    return {
        "s": timedelta(seconds=n),
        "m": timedelta(minutes=n),
        "h": timedelta(hours=n),
        "d": timedelta(days=n),
    }[unit]


def load_honcho_config() -> dict[str, Any]:
    from plugins.memory.honcho.client import HonchoClientConfig
    cfg = HonchoClientConfig.from_global_config()
    return {
        "api_key": cfg.api_key,
        "base_url": cfg.base_url or "https://api.honcho.dev",
        "workspace_id": cfg.workspace_id,
        "session_name": (cfg.raw.get("hosts", {}).get("hermes", {}) or {}).get("sessionName"),
    }


def fetch_session_messages(
    client, workspace_id: str, session_id: str, limit: int = 50
) -> list[Any]:
    """Pull recent messages from the backend for a given session.

    Returns empty list on any error — the joiner should degrade gracefully
    when the backend is slow or the session doesn't exist yet.
    """
    try:
        sess = client.session(session_id)
        page = sess.messages(size=limit, reverse=True)
        # page.items is the current page only; iterating the SyncPage auto-pages
        # through the entire session history, which is very slow on large sessions.
        msgs = list(getattr(page, "items", []) or [])
        # Reverse-chronological from the server → flip to chronological for display
        msgs.reverse()
        return msgs
    except Exception as e:
        print(f"[backend fetch failed for {session_id}: {e}]", file=sys.stderr)
        return []


def nearest_backend_activity(
    messages: list[Any], ts: datetime, window_s: int = 30
) -> tuple[int, Any | None]:
    """Return (count of messages within ±window, nearest message).

    'Nearest' by wall-clock. Fuzzy by design — server and client clocks drift.
    """
    window = timedelta(seconds=window_s)
    nearby = []
    for m in messages:
        m_ts = getattr(m, "created_at", None)
        if m_ts is None:
            continue
        if isinstance(m_ts, str):
            m_ts = datetime.fromisoformat(m_ts.replace("Z", "+00:00"))
        if m_ts.tzinfo is None:
            m_ts = m_ts.replace(tzinfo=timezone.utc)
        if abs(m_ts - ts) <= window:
            nearby.append((abs(m_ts - ts), m))
    if not nearby:
        return (0, None)
    nearby.sort(key=lambda x: x[0])
    return (len(nearby), nearby[0][1])


def fmt_event(ev: dict[str, Any]) -> str:
    """Compact one-line rendering of a dialectic.return event."""
    ms = ev.get("ms", "?")
    chars = ev.get("chars", 0)
    reason = ev.get("empty_reason", "?")
    turn = ev.get("turn", "?")
    streak = ev.get("empty_streak")
    first = ev.get("first_turn")
    bits = [f"turn={turn}", f"ms={ms}", f"chars={chars}", f"reason={reason}"]
    if streak:
        bits.append(f"streak={streak}")
    if first:
        bits.append("first_turn")
    return " ".join(bits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tail", type=int, default=20, help="number of dialectic.return events to show (default 20)")
    ap.add_argument("--empty-only", action="store_true", help="only show events where chars=0")
    ap.add_argument("--since", type=parse_since, default=None, help="only events newer than this (e.g. 10m, 2h)")
    ap.add_argument("--session", default=None, help="filter to a specific Honcho session name")
    ap.add_argument("--no-backend", action="store_true", help="skip backend fetch; audit log only")
    ap.add_argument("--window", type=int, default=30, help="timestamp correlation window in seconds (default 30)")
    args = ap.parse_args()

    audit_path = get_hermes_home() / "logs" / "honcho-audit.log"
    events = read_audit(audit_path)

    # Show which session the init line knows about
    inits = [e for e in events if e["event"] == "init"]
    if inits:
        last_init = inits[-1]
        print(f"[audit] last init: session={last_init.get('session')} "
              f"mode={last_init.get('mode')} "
              f"dial_cadence={last_init.get('dial_cadence')} "
              f"depth={last_init.get('dial_depth')}")

    # Filter to dialectic.return (and chat.* siblings for HTTP timing)
    dr = [e for e in events if e["event"] in ("dialectic.return", "prewarm.return")]
    if args.since:
        cutoff = datetime.now(timezone.utc) - args.since
        dr = [e for e in dr if e["ts"] >= cutoff]
    if args.empty_only:
        dr = [e for e in dr if e.get("chars", 0) == 0]
    dr = dr[-args.tail:]

    if not dr:
        print("[no dialectic.return events match the filters]")
        return

    # Count empty reasons for a quick summary
    summary: dict[str, int] = {}
    for e in dr:
        summary[e.get("empty_reason", "?")] = summary.get(e.get("empty_reason", "?"), 0) + 1
    print(f"[{len(dr)} events | by reason: {summary}]\n")

    # Pair each dialectic.return with the most recent chat.return/exception
    chat_events = [e for e in events if e["event"] in ("chat.return", "chat.exception")]

    backend_messages = []
    if not args.no_backend:
        try:
            cfg = load_honcho_config()
            if cfg.get("api_key") and cfg.get("workspace_id"):
                from honcho import Honcho
                client = Honcho(
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"],
                    workspace_id=cfg["workspace_id"],
                )
                session_id = args.session or cfg.get("session_name") or "hermes-agent"
                backend_messages = fetch_session_messages(
                    client, cfg["workspace_id"], session_id
                )
                print(f"[backend] workspace={cfg['workspace_id']} session={session_id} "
                      f"messages={len(backend_messages)}\n")
            else:
                print("[backend] no honcho config; skipping fetch\n")
        except Exception as e:
            print(f"[backend fetch error: {e}]\n")

    # Print events. Pair each dialectic.return with the most recent preceding
    # chat.* event (consumed once, to avoid reusing one http timing for multiple
    # dialectic returns in the log).
    chat_queue = list(chat_events)  # will drain from front
    for ev in dr:
        ts = ev["ts"].strftime("%H:%M:%S")
        print(f"{ts}  {fmt_event(ev)}")

        # Find most recent chat event at or before this dialectic.return
        matched = None
        while chat_queue and chat_queue[0]["ts"] <= ev["ts"]:
            matched = chat_queue.pop(0)
        if matched is not None and (ev["ts"] - matched["ts"]).total_seconds() < 60:
            if matched["event"] == "chat.exception":
                print(f"           └─ http: EXCEPTION ms={matched.get('ms')} error={matched.get('error')}")
            else:
                print(f"           └─ http: ms={matched.get('ms')} chars={matched.get('chars')} empty={matched.get('empty')}")

        if backend_messages:
            count, nearest = nearest_backend_activity(
                backend_messages, ev["ts"], window_s=args.window
            )
            if nearest is not None:
                content = getattr(nearest, "content", "")[:80].replace("\n", " ")
                peer = getattr(nearest, "peer_name", "?")
                print(f"           └─ backend: {count} msg in ±{args.window}s | "
                      f"nearest: [{peer}] {content!r}")
            else:
                print(f"           └─ backend: no messages in ±{args.window}s window")
        print()


if __name__ == "__main__":
    main()
