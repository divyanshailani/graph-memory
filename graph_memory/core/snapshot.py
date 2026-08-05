import json
import os
from .engine import get_connection, calculate_effective_trust, init_db, query_decision_ledger

def generate_active_snapshot(db_path: str, max_tokens: int = 600, min_trust: float = 0.7) -> str:
    """
    Generates an ultra-dense, prompt-cache friendly Markdown snapshot of active high-trust nodes
    and decision history to auto-inject into agent system prompts on session startup.
    Inspired by Hermes MEMORY.md snapshot architecture.
    """
    if not os.path.exists(db_path):
        return "# Epistemic Graph Memory Snapshot\n(No active graph database found)\n"

    init_db(db_path)
    lines = ["# Epistemic Graph Memory Snapshot"]
    char_limit = max_tokens * 4

    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT id, label, properties, trust_score, last_verified_at, created_at
            FROM Nodes
            WHERE is_deleted = 0 AND status = 'active'
            ORDER BY trust_score DESC, last_verified_at DESC
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
