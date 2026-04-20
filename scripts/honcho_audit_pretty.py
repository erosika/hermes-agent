#!/usr/bin/env python3
"""Honcho audit-log pretty printer.

Groups events by session init and turn, renders human-friendly output
with colored severity. Stdlib only. Reads ~/.hermes/logs/honcho-audit.log
by default.

Usage:
    python scripts/honcho_audit_pretty.py            # render whole log
    python scripts/honcho_audit_pretty.py -f         # follow (like tail -f)
    python scripts/honcho_audit_pretty.py --since 1h # last hour only
    python scripts/honcho_audit_pretty.py --session eribarrett
    python scripts/honcho_audit_pretty.py --no-color

The wire format is pipe-delimited:
    2026-04-20T16:12:11.085Z | event.name | key=value | key=value | ...
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

# ---------- ANSI ----------

_ISATTY = sys.stdout.isatty()


class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def paint(text: str, *codes: str, enabled: bool = True) -> str:
    if not enabled or not codes:
        return text
    return "".join(codes) + text + C.RESET


# ---------- parsing ----------

# 2026-04-20T16:12:11.085Z | event.name | key=value | key="quoted value"
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)\s*\|\s*"
    r"(?P<event>[a-z_][a-z0-9_.]*)\s*"
    r"(?:\|\s*(?P<rest>.*))?$"
)
_FIELD_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s|]+)')


def parse_line(line: str) -> dict | None:
    m = _LINE_RE.match(line.rstrip("\n"))
    if not m:
        return None
    out = {"ts": m.group("ts"), "event": m.group("event"), "_raw": line.rstrip("\n")}
    rest = m.group("rest") or ""
    for fm in _FIELD_RE.finditer(rest):
        k, v = fm.group(1), fm.group(2)
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1].replace('\\"', '"').replace("\\n", "\n")
        out[k] = v
    return out


def parse_ts(ts: str) -> datetime:
    # Drop trailing Z, parse as UTC.
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


# ---------- rendering ----------


def _hhmmss(ts: str) -> str:
    return ts[11:23]  # HH:MM:SS.mmm


def _ms(v: str | None) -> str:
    if not v:
        return ""
    try:
        ms = int(v)
    except ValueError:
        return v
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def _severity(ev: dict) -> str:
    """Return one of: 'ok', 'empty', 'warn', 'error', 'skip', 'info'."""
    e = ev["event"]
    if e in ("dialectic.return", "prewarm.return"):
        reason = ev.get("empty_reason", "ok")
        if reason == "ok":
            return "ok"
        if reason == "backend_empty":
            return "empty"
        if reason == "exception":
            return "error"
        return "warn"
    if e == "chat.exception" or e.endswith(".failed"):
        return "error"
    if e == "prefetch.timeout":
        return "warn"
    if e.endswith(".skip") or e == "stale.discard":
        return "skip"
    if e == "chat.skip":
        return "skip"
    return "info"


def render_event(ev: dict, color: bool) -> str | None:
    """Return one rendered line, or None to suppress."""
    e = ev["event"]
    sev = _severity(ev)
    t = _hhmmss(ev["ts"])

    # Color mapping
    sev_color = {
        "ok": C.GREEN,
        "empty": C.YELLOW,
        "warn": C.YELLOW,
        "error": C.RED,
        "skip": C.GRAY,
        "info": C.CYAN,
    }[sev]

    t_fmt = paint(t, C.DIM, enabled=color)

    if e == "init":
        session = ev.get("session", "?")
        return f"{t_fmt}  {paint('init', C.BOLD, C.CYAN, enabled=color)}  session={session}"

    if e == "config.explain":
        summary = ev.get("summary", "")
        return f"{' ' * 14}{paint(summary, C.DIM, enabled=color)}"

    if e == "turn.begin":
        # Handled by the grouper — suppress here.
        return None

    if e == "prewarm.start":
        return (
            f"{t_fmt}  {paint('prewarm', C.BLUE, enabled=color)}  "
            f"{paint('start', C.DIM, enabled=color)}  session={ev.get('session', '?')}"
        )

    if e == "prewarm.return":
        reason = ev.get("empty_reason", "ok")
        chars = ev.get("chars", "0")
        ms = _ms(ev.get("ms"))
        label = paint("ok" if reason == "ok" else reason, sev_color, enabled=color)
        return f"{t_fmt}  {paint('prewarm', C.BLUE, enabled=color)}  {label}  {ms} · {chars} chars"

    if e == "prewarm.wait":
        tmo = ev.get("timeout", "?")
        return (
            f"{t_fmt}  {paint('prewarm', C.BLUE, enabled=color)}  "
            f"{paint('wait', C.DIM, enabled=color)}  "
            f"{paint(f'first-turn waiting for prewarm to land (≤{tmo}s)', C.DIM, enabled=color)}"
        )

    if e == "prewarm.still_running":
        tmo = ev.get("timeout", "?")
        return (
            f"{t_fmt}  {paint('prewarm', C.BLUE, enabled=color)}  "
            f"{paint('slow', C.YELLOW, enabled=color)}  "
            f"still running past {tmo}s — deferring to next turn (no duplicate fire)"
        )

    if e == "dialectic.return":
        reason = ev.get("empty_reason", "ok")
        chars = ev.get("chars", "0")
        ms = _ms(ev.get("ms"))
        first = ev.get("first_turn") == "true"
        streak = ev.get("empty_streak")

        if reason == "ok":
            lbl = paint("ok", C.GREEN, enabled=color)
            tail = f"{ms} · {chars} chars"
        elif reason == "backend_empty":
            lbl = paint("EMPTY", C.YELLOW, C.BOLD, enabled=color)
            tail = f"{ms} · backend returned nothing"
            if streak:
                tail += paint(f"  (streak={streak}, next fire widened)", C.DIM, enabled=color)
        elif reason == "exception":
            lbl = paint("ERROR", C.RED, C.BOLD, enabled=color)
            tail = f"{ms} · {ev.get('error', '?')}"
            if streak:
                tail += paint(f"  (streak={streak})", C.DIM, enabled=color)
        else:
            lbl = paint(reason, sev_color, enabled=color)
            tail = f"{ms} · {chars} chars"

        prefix = "dialectic"
        if first:
            prefix = paint("dialectic*", C.MAGENTA, enabled=color)
        else:
            prefix = paint("dialectic", C.MAGENTA, enabled=color)
        return f"{t_fmt}  {prefix}  {lbl}  {tail}"

    if e == "prefetch.fire":
        qlen = ev.get("query_len", "?")
        depth = ev.get("depth", "?")
        first = ev.get("first_turn") == "true"
        tag = "fire*" if first else "fire"
        return (
            f"{t_fmt}  {paint('prefetch', C.BLUE, enabled=color)}  "
            f"{paint(tag, C.DIM, enabled=color)}  qlen={qlen} depth={depth}"
        )

    if e == "prefetch.timeout":
        timeout = ev.get("timeout", "?")
        return (
            f"{t_fmt}  {paint('prefetch', C.BLUE, enabled=color)}  "
            f"{paint('TIMEOUT', C.YELLOW, C.BOLD, enabled=color)}  "
            f"watchdog fired at {timeout}s"
        )

    if e == "prefetch.skip":
        reason = ev.get("reason", "?")
        extras = []
        for k in ("effective", "base", "empty_streak", "since_last", "thread_age_ms"):
            if k in ev:
                extras.append(f"{k}={ev[k]}")
        tail = " ".join(extras)
        return (
            f"{t_fmt}  {paint('prefetch', C.BLUE, enabled=color)}  "
            f"{paint('skip', C.DIM, enabled=color)}  "
            f"{paint(reason, C.DIM, enabled=color)}  {paint(tail, C.DIM, enabled=color)}"
        )

    if e == "context.fire":
        return f"{t_fmt}  {paint('context', C.CYAN, enabled=color)}  {paint('fire', C.DIM, enabled=color)}"

    if e == "context.fire_failed":
        return (
            f"{t_fmt}  {paint('context', C.CYAN, enabled=color)}  "
            f"{paint('ERROR', C.RED, C.BOLD, enabled=color)}  {ev.get('error', '?')}"
        )

    if e == "chat.return":
        # Lower-level event from session.py — fold into dialectic summary.
        # Showing every one is noisy; dialectic.return already summarizes.
        return None

    if e == "chat.skip":
        return (
            f"{t_fmt}  {paint('chat', C.GRAY, enabled=color)}  "
            f"{paint('skip', C.GRAY, enabled=color)}  "
            f"reason={ev.get('reason', '?')}"
        )

    if e == "chat.exception":
        return (
            f"{t_fmt}  {paint('chat', C.GRAY, enabled=color)}  "
            f"{paint('EXCEPTION', C.RED, C.BOLD, enabled=color)}  {ev.get('error', '?')}"
        )

    if e == "stale.discard":
        return (
            f"{t_fmt}  {paint('stale', C.GRAY, enabled=color)}  "
            f"discarded dialectic from turn {ev.get('fired_at', '?')} "
            f"({ev.get('chars', '?')} chars)"
        )

    if e == "inject.build":
        base = int(ev.get("base_chars", 0) or 0)
        dial = int(ev.get("dial_chars", 0) or 0)
        fired_at = ev.get("dial_fired_at", "-")
        total = ev.get("total_after", "?")
        reused = ev.get("reused") == "true"
        turn = ev.get("turn", "?")

        if dial == 0:
            marker = paint("∅", C.DIM, enabled=color)
            origin = paint("(no dialectic this turn)", C.DIM, enabled=color)
        else:
            if reused:
                origin = paint(f"← reused from turn {fired_at}", C.DIM, enabled=color)
                marker = paint("◇", C.GREEN, enabled=color)
            else:
                if fired_at == "0":
                    origin = paint("← prewarm", C.GREEN, enabled=color)
                else:
                    origin = paint(f"← fresh (turn {fired_at})", C.GREEN, C.BOLD, enabled=color)
                marker = paint("◆", C.GREEN, C.BOLD, enabled=color)

        return (
            f"{t_fmt}  {paint('inject', C.GREEN, enabled=color)}  {marker}  "
            f"base={base} + dial={dial} {origin} → total={total}"
        )

    if e == "inject.empty":
        return (
            f"{t_fmt}  {paint('inject', C.GREEN, enabled=color)}  "
            f"{paint('empty', C.YELLOW, enabled=color)}  no context this turn"
        )

    # Fallback: dump the raw line (but dim).
    return paint(ev["_raw"], C.DIM, enabled=color)


# ---------- grouping ----------


def render_stream(events: Iterable[dict], color: bool = True) -> Iterator[str]:
    """Yield rendered lines, inserting turn headers as new turns appear."""
    current_turn: str | None = None
    saw_config_explain_after_init = False
    last_was_blank = True

    for ev in events:
        e = ev["event"]

        # New session init resets turn tracking and emits a divider.
        if e == "init":
            if not last_was_blank:
                yield ""
            bar = "━" * 72
            yield paint(bar, C.CYAN, enabled=color)
            current_turn = None
            saw_config_explain_after_init = False

        # Turn boundary: insert a header.
        if e == "turn.begin":
            turn = ev.get("turn", "?")
            if turn != current_turn:
                current_turn = turn
                if not last_was_blank:
                    yield ""
                preview = ev.get("preview", "")
                qlen = ev.get("query_len", "?")
                header = f"─ turn {turn} ─"
                if preview:
                    header += f' "{preview}"'
                header += f"  (qlen={qlen})"
                yield paint(header, C.BOLD, C.MAGENTA, enabled=color)
                last_was_blank = False
            continue  # turn.begin has no body line

        rendered = render_event(ev, color=color)
        if rendered is None:
            continue
        yield rendered
        last_was_blank = False


# ---------- input sources ----------


def tail_file(path: Path, follow: bool, from_offset: int = 0) -> Iterator[str]:
    """Yield lines from path. If follow, keep yielding as the file grows."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(from_offset)
        while True:
            line = f.readline()
            if line:
                yield line
                continue
            if not follow:
                return
            time.sleep(0.25)
            # Handle rotation: if the file shrank, reopen.
            try:
                if path.stat().st_size < f.tell():
                    f.close()
                    f = open(path, "r", encoding="utf-8", errors="replace")
            except FileNotFoundError:
                time.sleep(0.5)


def parse_since(spec: str) -> datetime:
    """Accept '1h', '30m', '2d', or ISO timestamp."""
    now = datetime.now(timezone.utc)
    m = re.fullmatch(r"(\d+)([smhd])", spec)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return now - timedelta(seconds=n * mult)
    try:
        dt = datetime.fromisoformat(spec)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise SystemExit(f"Unrecognized --since value: {spec!r}")


# ---------- main ----------


def default_log_path() -> Path:
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home) / "logs" / "honcho-audit.log"
    return Path.home() / ".hermes" / "logs" / "honcho-audit.log"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pretty-print the Honcho audit log, grouped by turn."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(default_log_path()),
        help="Path to honcho-audit.log (default: $HERMES_HOME/logs/honcho-audit.log)",
    )
    parser.add_argument(
        "-f", "--follow", action="store_true", help="Keep reading as the log grows."
    )
    parser.add_argument(
        "--since", metavar="WHEN",
        help="Only show events since WHEN (e.g. '1h', '30m', '2d', or ISO timestamp).",
    )
    parser.add_argument(
        "--session", metavar="NAME",
        help="Only show blocks for sessions matching NAME (substring match on init/prewarm rows).",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable ANSI color output."
    )
    args = parser.parse_args(argv)

    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"Log not found: {path}", file=sys.stderr)
        return 1

    color = (not args.no_color) and _ISATTY
    since_dt: datetime | None = parse_since(args.since) if args.since else None
    session_filter = args.session.lower() if args.session else None

    # Session filtering is block-scoped: once we see an init/prewarm.start
    # matching the filter, show all events until the next init that doesn't match.
    active_session_matches = session_filter is None

    def source() -> Iterator[dict]:
        nonlocal active_session_matches
        for raw in tail_file(path, follow=args.follow):
            ev = parse_line(raw)
            if ev is None:
                continue
            if since_dt is not None:
                try:
                    if parse_ts(ev["ts"]) < since_dt:
                        continue
                except ValueError:
                    pass

            if session_filter is not None:
                if ev["event"] == "init":
                    sess = ev.get("session", "").lower()
                    active_session_matches = session_filter in sess
                elif ev["event"] == "prewarm.start":
                    sess = ev.get("session", "").lower()
                    if session_filter in sess:
                        active_session_matches = True
                if not active_session_matches:
                    continue

            yield ev

    try:
        for line in render_stream(source(), color=color):
            print(line, flush=args.follow)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
