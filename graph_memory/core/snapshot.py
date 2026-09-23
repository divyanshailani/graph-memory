import os
import json
import hashlib
from .engine import get_connection, write_transaction, calculate_effective_trust, init_db, query_decision_ledger, detect_contradictions, now_iso

# Bounded candidate pool. The pool is ranked in SQL (trust first, then recency) and
# filtered in Python by exact effective trust; an ID-ordered LIMIT window is
# meaningless at scale — it silently returned only the alphabetically first 50 IDs.
CANDIDATE_LIMIT = 2000


def _describe(props: dict, node_id: str) -> tuple:
    """Returns (text, is_prose) for the most informative summary a node carries.

    Prose (a knowledge card's description or title, a distilled fact) is what belongs
    in an injected prompt; a component's bare name is a fallback. An empty text means
    the node carries nothing but its own ID — a file listing is not memory.
    """
    version, changes = props.get("version"), props.get("changes")
    if version and isinstance(changes, list) and changes:
        head = f"v{version}" + (f' "{props["codename"]}"' if props.get("codename") else "")
        more = f" (+{len(changes) - 1} more)" if len(changes) > 1 else ""
        return f"{head}: {changes[0]}{more}", True

    for key in ("description", "summary", "title"):
        value = props.get(key)
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in list(value)[:3])
        if value and str(value) != node_id:
            return str(value), True

    for key in ("name", "pattern"):
        value = props.get(key)
        if value and str(value) != node_id:
            return str(value), False

    return "", False


def _rank(item):
    """Curated knowledge, then prose facts, then bare code identifiers — and within a
    tier, higher effective trust first with the ID as a stable tie-break. The snapshot
    is injected into a system prompt, so a memory card must not lose its slot to a
    class stub of equal trust."""
    eff_trust, node_id, _entry, label, is_prose = item
    if label == "Knowledge_Node":
        tier = 0
    elif is_prose:
        tier = 1
    else:
        tier = 2
    return (tier, -eff_trust, node_id)


def _render_snapshot_body(db_path: str, max_tokens: int, min_trust: float) -> str:
    """Renders the snapshot deterministically (nodes ranked by tier and trust, ties
    broken by stable ID, never by volatile timestamps) so the same graph state always
    produces the same text."""
    init_db(db_path)
    lines = ["# Epistemic Graph Memory Snapshot"]
    char_limit = max_tokens * 4

    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT id, label, properties, trust_score, last_verified_at
            FROM Nodes
            WHERE is_deleted = 0 AND status = 'active'
            ORDER BY trust_score DESC, last_verified_at DESC, id ASC
            LIMIT ?
        """, (CANDIDATE_LIMIT,)).fetchall()

        facts = []
        milestones = []

        for node_id, label, props_json, base_trust, last_verified in rows:
            if label in ("Fact_Node", "Knowledge_Node"):
                bucket = facts
            elif label in ("Episode_Node", "Release_Node"):
                bucket = milestones
            else:
                continue

            eff_trust = calculate_effective_trust(base_trust, last_verified)
            if eff_trust < min_trust:
                continue

            props = json.loads(props_json) if props_json else {}
            desc, is_prose = _describe(props, node_id)
            if not desc:
                continue

            bucket.append(
                (eff_trust, node_id, f"[{node_id}] {desc} (Trust: {eff_trust:.2f})", label, is_prose)
            )

        for bucket in (facts, milestones):
            bucket.sort(key=_rank)

        if facts:
            lines.append("\n## Active Verified Facts")
            for item in facts[:15]:
                lines.append(f"- {item[2]}")

        if milestones:
            lines.append("\n## Project Milestones & Releases")
            for item in milestones[:10]:
                lines.append(f"- {item[2]}")

        decisions = query_decision_ledger(db_path, limit=5)
        if decisions:
            lines.append("\n## Recent Multi-Agent Decisions")
            for d in decisions:
                lines.append(f"- [{d['timestamp']}] {d['agent_name']}: {d['node_id']} -> {d['rationale']}")

        contradictions = detect_contradictions(db_path, limit=3)
        if contradictions:
            lines.append("\n## ⚠ Conflicting Assertions (agents disagree — verify before relying)")
            for c in contradictions:
                latest = c["conflicts"][-1]
                lines.append(
                    f"- ⚠ [{c['node_id']}] {latest['key']}: '{latest['old']}' vs '{latest['new']}' (last: {latest['agent']})"
                )

    result = "\n§\n".join(lines)
    if len(result) > char_limit:
        result = result[:char_limit] + "\n...[truncated for token budget]"
    return result


def generate_active_snapshot(db_path: str, max_tokens: int = 600, min_trust: float = 0.7) -> str:
    """
    Generates an ultra-dense, prompt-cache friendly Markdown snapshot of active high-trust nodes
    and decision history to auto-inject into agent system prompts on session startup.

    Prompt-cache stability: rendering is deterministic, and the result is fingerprinted
    (graph content + generation parameters). If nothing relevant changed since the last
    render — including effective-trust values at display precision — the cached snapshot is
    returned byte-for-byte, so agent system prompts keep their prompt-cache prefix intact.
    """
    if not os.path.exists(db_path):
        return "# Epistemic Graph Memory Snapshot\n(No active graph database found)\n"

    body = _render_snapshot_body(db_path, max_tokens, min_trust)
    fingerprint = hashlib.sha256(
        f"{max_tokens}|{min_trust}|{body}".encode("utf-8")
    ).hexdigest()

    with get_connection(db_path) as conn:
        cached = conn.execute(
            "SELECT fingerprint, content FROM Snapshot_Cache WHERE id = 1"
        ).fetchone()
        if cached and cached[0] == fingerprint:
            return cached[1]

        with write_transaction(conn):
            conn.execute(
                """
                INSERT INTO Snapshot_Cache (id, fingerprint, content, generated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    content = excluded.content,
                    generated_at = excluded.generated_at
                """,
                (fingerprint, body, now_iso()),
            )

    return body
