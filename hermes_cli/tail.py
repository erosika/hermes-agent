"""Tail recent session messages from the existing SessionDB store.

References issue #1155 as the lightweight, sessions-backed observability path.
"""

from __future__ import annotations

from datetime import datetime
import json
import time

from hermes_state import SessionDB


def _format_timestamp(ts) -> str:
    if not ts:
        return "--:--:--"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "--:--:--"


def _truncate(text: str, limit: int = 180) -> str:
    text = (text or "").replace("\n", " ⏎ ").strip()
    if not text:
        return "(no content)"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _summarize_tool_json(content: str) -> str | None:
    try:
        data = json.loads(content)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    parts = []
    if "success" in data:
        parts.append("ok" if data.get("success") else "error")
    if "exit_code" in data:
        parts.append(f"exit={data.get('exit_code')}")
    if "error" in data and data.get("error"):
        parts.append(_truncate(str(data.get("error")), 80))
    elif "output" in data and data.get("output"):
        parts.append(_truncate(str(data.get("output")), 120))
    elif "result" in data and data.get("result"):
        parts.append(_truncate(str(data.get("result")), 120))

    if not parts:
        return None
    return " · ".join(parts)


def _format_message_line(msg: dict) -> str:
    role = msg.get("role") or "message"
    tool_name = msg.get("tool_name")
    role_markers = {
        "user": "▸",
        "assistant": "◂",
        "tool": "⚙",
        "system": "◆",
    }
    marker = role_markers.get(role, "•")
    if role == "tool" and tool_name:
        label = f"tool:{tool_name}"
    else:
        label = role

    content = (msg.get("content") or "").strip()
    if role == "tool":
        content = _summarize_tool_json(content) or content

    if not content and msg.get("tool_calls"):
        names = []
        for tc in msg.get("tool_calls") or []:
            try:
                names.append(tc["function"]["name"])
            except Exception:
                continue
        if names:
            content = "tool calls -> " + ", ".join(names)

    content = _truncate(content)
    return f"[{_format_timestamp(msg.get('timestamp'))}] {marker} {label:<14} {content}"


def _resolve_session_id(db: SessionDB, session: str | None, source: str | None) -> str | None:
    if session:
        resolved = db.resolve_session_id(session)
        if resolved:
            return resolved
        return db.resolve_session_by_title(session)

    source_filter = None if source in (None, "all") else source
    sessions = db.search_sessions(source=source_filter, limit=1)
    if sessions:
        return sessions[0]["id"]
    return None


def _print_header(session_meta: dict, shown_count: int, follow: bool) -> None:
    title = (session_meta.get("title") or "").strip() or "(untitled)"
    source = session_meta.get("source") or "?"
    session_id = session_meta.get("id") or "(unknown)"
    message_count = session_meta.get("message_count")

    print("⚕ Hermes tail")
    print(f"  session:  {session_id}")
    print(f"  source:   {source}")
    print(f"  title:    {title}")
    if message_count is not None:
        print(f"  messages: {message_count}")
    print(f"  showing last {shown_count} message(s)")
    if follow:
        print("  following for new messages — Ctrl-C to stop")
    print()


def tail_command(args) -> None:
    db = SessionDB()
    try:
        session_arg = getattr(args, "session", None)
        source = getattr(args, "source", None) or "cli"
        limit = max(1, int(getattr(args, "limit", 20) or 20))
        follow = bool(getattr(args, "follow", False))
        poll_interval = float(getattr(args, "poll_interval", 1.0) or 1.0)

        session_id = _resolve_session_id(db, session_arg, source)
        if not session_id:
            if session_arg:
                print(f"Session '{session_arg}' not found.")
            else:
                print(f"No {source} sessions found.")
            return

        session_meta = db.get_session(session_id) or {"id": session_id}
        recent_messages = db.get_recent_messages(session_id, limit=limit)
        _print_header(session_meta, len(recent_messages), follow)

        if not recent_messages:
            print("(no messages yet)")
            if not follow:
                return
            print("(waiting for first message)")
            last_id = 0
        else:
            last_id = 0
            for msg in recent_messages:
                print(_format_message_line(msg))
                last_id = max(last_id, int(msg.get("id") or 0))

            if not follow:
                return

        while True:
            messages = db.get_messages_since(session_id, after_id=last_id, limit=limit)
            for msg in messages:
                print(_format_message_line(msg))
                last_id = max(last_id, int(msg.get("id") or 0))

            try:
                time.sleep(max(0.05, poll_interval))
            except KeyboardInterrupt:
                print()
                print("(stopped tailing)")
                break
    finally:
        db.close()
