import os
import json
import hashlib
from .engine import get_connection, write_transaction, calculate_effective_trust, init_db, query_decision_ledger, now_iso


def _render_snapshot_body(db_path: str, max_tokens: int, min_trust: float) -> str:
    """Renders the snapshot deterministically (nodes ordered by stable ID, never by
    volatile timestamps) so the same graph state always produces the same text."""
    init_db(db_path)
    lines = ["# Epistemic Graph Memory Snapshot"]
    char_limit = max_tokens * 4

    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT id, label, properties, trust_score, last_verified_at, created_at
            FROM Nodes
            WHERE is_deleted = 0 AND status = 'active'
            ORDER BY id ASC
            LIMIT 50
        """).fetchall()

        facts = []
        milestones = []
        components = []

        for r in rows:
            node_id, label, props_json, base_trust, last_verified, created_at = r
            eff_trust = calculate_effective_trust(base_trust, last_verified)
            if eff_trust < min_trust:
                continue

            props = json.loads(props_json) if props_json else {}
            desc = props.get("description") or props.get("summary") or props.get("changes") or props.get("name") or node_id

            entry = f"[{node_id}] {desc} (Trust: {eff_trust:.2f})"
            if label in ("Fact_Node", "Knowledge_Node"):
                facts.append(entry)
            elif label in ("Episode_Node", "Release_Node"):
                milestones.append(entry)
            else:
                components.append(entry)

        if facts:
            lines.append("\n## Active Verified Facts")
            for f in facts[:15]:
                lines.append(f"- {f}")

        if milestones:
            lines.append("\n## Project Milestones & Releases")
            for m in milestones[:10]:
                lines.append(f"- {m}")

        decisions = query_decision_ledger(db_path, limit=5)
        if decisions:
            lines.append("\n## Recent Multi-Agent Decisions")
            for d in decisions:
                lines.append(f"- [{d['timestamp']}] {d['agent_name']}: {d['node_id']} -> {d['rationale']}")

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
