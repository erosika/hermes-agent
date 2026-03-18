"""Audit query tool — lets the agent inspect its own audit trail.

Registered as ``audit_query`` in the ``audit`` toolset.  Always available
when audit logging is enabled (no check_fn gate — the module gracefully
returns empty results when disabled).
"""

import json

from tools.registry import registry

_SCHEMA = {
    "name": "audit_query",
    "description": (
        "Query the audit log for recent agent actions, errors, tool usage, "
        "and system health. Use when the user asks about what happened, what "
        "errors occurred, recent tool usage, or overall system status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["query", "summary", "problems"],
                "description": (
                    "query: list recent events with optional filters. "
                    "summary: aggregate stats (tokens, cost, error rate, top tools). "
                    "problems: auto-detect anomalies (repeated errors, rate limits, slow tools)."
                ),
            },
            "type": {
                "type": "string",
                "description": "Filter by event type: tool.call, api.request, tool.error, honcho.sync, etc.",
            },
            "tool": {
                "type": "string",
                "description": "Filter by tool name: terminal, read_file, patch, etc.",
            },
            "keyword": {
                "type": "string",
                "description": "Text search across event payloads.",
            },
            "session": {
                "type": "string",
                "description": "Scope to a specific session ID.",
            },
            "limit": {
                "type": "integer",
                "description": "Max events to return (default 20, max 100).",
            },
        },
        "required": ["action"],
    },
}


def _handle_audit_query(**kwargs) -> str:
    """Handle audit_query tool calls."""
    try:
        from agent.audit import query_events, audit_summary, audit_problems
    except ImportError:
        return json.dumps({"error": "Audit module not available"})

    action = kwargs.get("action", "query")
    session_id = kwargs.get("session")
    limit = min(kwargs.get("limit") or 20, 100)

    try:
        if action == "summary":
            s = audit_summary(session_id=session_id)
            if s.get("total", 0) == 0:
                return "No audit events found."
            lines = [f"Audit summary: {s['total']} events, {s['sessions']} sessions"]
            lines.append(f"API: {s['api_calls']} calls, {s['total_tokens']:,} tokens, ${s['total_cost_usd']:.4f}")
            lines.append(f"Tools: {s['tool_calls']} calls, Errors: {s['errors']} ({s['error_rate']}%)")
            if s.get("top_tools"):
                lines.append("Top tools: " + ", ".join(f"{t['tool']}({t['count']})" for t in s["top_tools"]))
            if s.get("top_errors"):
                lines.append("Top errors: " + ", ".join(f"{e['error'][:40]}(x{e['count']})" for e in s["top_errors"]))
            return "\n".join(lines)

        elif action == "problems":
            findings = audit_problems(session_id=session_id)
            if not findings:
                return "No problems detected."
            lines = [f"{len(findings)} problem(s) detected:"]
            for f in findings:
                lines.append(f"  [{f['rule']}] {f['message']}")
            return "\n".join(lines)

        else:  # query
            events = query_events(
                session_id=session_id,
                event_type=kwargs.get("type"),
                tool_name=kwargs.get("tool"),
                keyword=kwargs.get("keyword"),
                limit=limit,
            )
            if not events:
                return "No matching audit events."
            lines = [f"{len(events)} events:"]
            for e in events:
                ts = e.get("iso", "")[:19]
                etype = e.get("type", "?")
                tool = e.get("tool", "")
                err = e.get("error", "")
                dur = e.get("duration_ms")
                detail = ""
                if tool:
                    detail = f" {tool}"
                if dur:
                    detail += f" {dur:.0f}ms"
                if err:
                    detail += f" ERR: {err[:60]}"
                lines.append(f"  {ts} {etype}{detail}")
            # Truncate to avoid context bloat
            result = "\n".join(lines)
            return result[:4000]

    except Exception as e:
        return f"Audit query failed: {e}"


registry.register(
    name="audit_query",
    toolset="audit",
    schema=_SCHEMA,
    handler=_handle_audit_query,
)
