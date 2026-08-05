import re
from .engine import get_or_create_node, add_observation, record_decision_ledger, log_session_message

def distill_session_exchanges(db_path: str, session_id: str, agent_name: str, exchanges: list) -> dict:
    """
    Continuous micro-compactor & memory distiller inspired by Hermes Agent architecture.
    
    Asymmetric Principle:
    - User prompts are NEVER compacted (verbatim user intent is preserved in session logs).
    - Assistant tool outputs and large file reads are continuously distilled into dense,
      structured Fact_Node entries and stored in Graph Memory.
    """
    nodes_updated = []
    distilled_count = 0

    for exchange in exchanges:
        role = exchange.get("role", "user")
        content = exchange.get("content", "")

        # Always log verbatim message into episodic Session_Logs (FTS5 indexed)
        log_session_message(db_path, session_id, agent_name, role, content)

        # Distill assistant turns containing facts, code edits, or decisions
        if role in ("assistant", "tool"):
            # Extract key patterns: file edits, bug fixes, releases, decisions
            facts = extract_facts_from_text(content)
            for fact_id, fact_data in facts.items():
                get_or_create_node(
                    db_path=db_path,
                    node_id=fact_id,
                    label="Fact_Node",
                    properties={
                        "description": fact_data["desc"],
                        "source": "Session_Distillation",
                        "session_id": session_id
                    },
                    trust_score=0.9,
                    verification_method="session_distill",
                    agent_name=agent_name,
                    rationale=f"Distilled from session {session_id}"
                )
                nodes_updated.append(fact_id)
                distilled_count += 1

    return {
        "session_id": session_id,
        "distilled_facts_count": distilled_count,
        "nodes_updated": list(set(nodes_updated))
    }

def extract_facts_from_text(text: str) -> dict:
    """Helper regex/text pattern extractor for fact distillation."""
    facts = {}
    
    # Catch explicit [Fact: ...] or [Decision: ...] patterns
    matches = re.findall(r'\[(Fact|Decision|Milestone):\s*([^\]]+)\]', text, re.IGNORECASE)
    for category, detail in matches:
        clean_id = f"{category}_{re.sub(r'[^a-zA-Z0-9_]', '_', detail)[:40]}"
        facts[clean_id] = {"desc": detail.strip()}

    # Catch fix/release lines
    fix_matches = re.findall(r'(?:fixed|resolved|implemented|released)\s+([A-Za-z0-9_\-\.\s]{5,50})', text, re.IGNORECASE)
    for item in fix_matches[:3]:
        clean_id = f"Fact_{re.sub(r'[^a-zA-Z0-9_]', '_', item).strip('_')[:40]}"
        if clean_id not in facts:
            facts[clean_id] = {"desc": f"Automated distillation: {item.strip()}"}

    return facts
