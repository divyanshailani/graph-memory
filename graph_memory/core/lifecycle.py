"""
Harness-agnostic lifecycle dispatcher (v3.5.0).

A single entrypoint — `graph-memory hook-event` (reads a hook payload as JSON on
stdin) — that any agent harness can call on its lifecycle events. The payload
shape follows the Claude Code / ZCode hook convention (`hook_event_name`,
`tool_name`, `tool_input`, `session_id`, `transcript_path`), but any payload
carrying those fields works.

Event mapping:
- PostToolUse (Write/Edit/MultiEdit/ApplyPatch) -> incremental AST ingest of the
  edited file (<5ms), keeping the code graph live with zero agent effort.
- Stop / SessionEnd -> best-effort episodic capture: the transcript tail is
  logged into Session_Logs (FTS5) and assistant turns are distilled into graph
  facts, then installed snapshot files are refreshed.
- SessionStart -> refreshes the auto-memory snapshot files of every installed
  framework so sessions begin with current memory.

Output contract: hooks must stay silent (strict JSON-output schemas like ZCode's
reject stray stdout), so nothing is printed on success; errors go to stderr and
the process still exits 0 unless the dispatcher itself is misused.
"""
import json
import sys

from graph_memory.core.engine import get_db_path as _engine_db_path, log_session_message, get_or_create_node
from graph_memory.core.distill import extract_facts_from_text

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "ApplyPatch", "write_file", "edit_file", "str_replace_editor"}
TRANSCRIPT_TAIL_LINES = 200
MAX_DISTILL_FACTS = 10


def handle_hook_event(payload: dict, db_path: str = None) -> dict:
    """Dispatches a single hook payload. Returns a summary dict; never raises on bad payloads."""
    db_path = db_path or _engine_db_path()
    event = (payload.get("hook_event_name") or payload.get("event") or "").lower()

    if event == "posttooluse":
        return _handle_post_tool_use(payload, db_path)
    if event in ("stop", "sessionend", "session_end"):
        return _handle_stop(payload, db_path)
    if event in ("sessionstart", "session_start"):
        return _handle_session_start(payload, db_path)

    return {"status": "ignored", "event": event or "unknown"}


def _handle_post_tool_use(payload: dict, db_path: str) -> dict:
    from graph_memory.core.ingest import ingest_file

    tool = payload.get("tool_name") or ""
    if tool and tool not in EDIT_TOOLS:
        return {"status": "ignored", "reason": f"tool '{tool}' does not modify files"}

    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("filePath")
        or tool_input.get("path")
        or payload.get("file_path")
    )
    if not file_path:
        return {"status": "ignored", "reason": "no file_path in payload"}

    try:
        res = ingest_file(
            db_path,
            file_path,
            agent_name=payload.get("agent_name") or "Hook-PostToolUse",
            rationale=f"Auto-ingest after {tool or 'edit'} via hook",
        )
        return {"status": res.get("status", "ok"), "file": file_path, "detail": res.get("message", "")}
    except Exception as e:  # never break the host harness
        print(f"[graph-memory] post-tool-use ingest failed: {e}", file=sys.stderr)
        return {"status": "error", "reason": str(e)}


def _handle_stop(payload: dict, db_path: str) -> dict:
    session_id = payload.get("session_id") or payload.get("sessionId") or "default_session"
    agent_name = payload.get("agent_name") or payload.get("agentName") or "Hook-SessionEnd"
    transcript_path = payload.get("transcript_path") or payload.get("transcriptPath")

    turns_logged = 0
    facts_distilled = 0
    if transcript_path:
        try:
            turns_logged, facts_distilled = _capture_transcript(
                db_path, transcript_path, session_id, agent_name
            )
        except Exception as e:
            print(f"[graph-memory] transcript capture failed: {e}", file=sys.stderr)

    try:
        from graph_memory.integrations.framework_hooks import refresh_installed_snapshots
        refresh_installed_snapshots(db_path)
    except Exception as e:
        print(f"[graph-memory] snapshot refresh failed: {e}", file=sys.stderr)

    return {"status": "ok", "turns_logged": turns_logged, "facts_distilled": facts_distilled}


def _handle_session_start(payload: dict, db_path: str) -> dict:
    try:
        from graph_memory.integrations.framework_hooks import refresh_installed_snapshots
        refresh_installed_snapshots(db_path)
        return {"status": "ok", "refreshed": True}
    except Exception as e:
        print(f"[graph-memory] snapshot refresh failed: {e}", file=sys.stderr)
        return {"status": "error", "reason": str(e)}


def _capture_transcript(db_path: str, transcript_path: str, session_id: str, agent_name: str) -> tuple:
    """Reads the tail of a JSONL transcript, logs user/assistant turns into
    Session_Logs (FTS5), and distills assistant text into graph facts."""
    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[-TRANSCRIPT_TAIL_LINES:]

    turns_logged = 0
    distilled = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        message = entry.get("message") or entry
        role = message.get("role") or entry.get("type") or ""
        if role not in ("user", "assistant"):
            continue

        content = message.get("content", "")
        if isinstance(content, list):  # Anthropic-style content blocks
            content = " ".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        content = (content or "").strip()
        if not content:
            continue

        log_session_message(db_path, session_id, agent_name, role, content)
        turns_logged += 1

        if role == "assistant":
            for fact_id, fact_data in list(extract_facts_from_text(content).items())[:MAX_DISTILL_FACTS]:
                get_or_create_node(
                    db_path,
                    fact_id,
                    "Fact_Node",
                    {
                        "description": fact_data["desc"],
                        "source": "Session_Distillation",
                        "session_id": session_id,
                    },
                    trust_score=0.9,
                    verification_method="session_distill",
                    agent_name=agent_name,
                    rationale=f"Distilled from session {session_id}",
                )
                distilled += 1

    return turns_logged, distilled


def main():
    """CLI entrypoint for `graph-memory hook-event`: reads one JSON payload from stdin."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    db_path = _engine_db_path()
    result = handle_hook_event(payload, db_path=db_path)
    # Silent on success: hook stdout schemas (e.g. ZCode) reject unrecognized output.
    if result.get("status") == "error":
        print(json.dumps(result), file=sys.stderr)
    sys.exit(0)
