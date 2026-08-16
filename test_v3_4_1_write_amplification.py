"""
v3.4.1 regression tests: Decision Ledger signal isolation & write amplification.

1. AST ingestion (deterministic parsing) must not flood the Decision_Ledger —
   it is an audit trail for agent decisions, not a parse log.
2. Node history arrays must be capped and consecutive-identical entries collapsed,
   so repeated re-ingestion never grows the properties JSON payload.
3. search_nodes must batch access-count feedback into one write instead of one
   transaction per result row.
"""
import json
from pathlib import Path
from graph_memory.core import engine, ingest


def _make_project(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (root / "main.py").write_text(
        "import os\n\n\ndef run():\n    return os.getcwd()\n", encoding="utf-8"
    )


def test_ingestion_writes_no_ledger_rows(tmp_path):
    project = tmp_path / "repo"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")

    ingest.ingest_codebase(db_path, str(project))

    with engine.get_connection(db_path) as conn:
        ledger_rows = conn.execute("SELECT COUNT(*) FROM Decision_Ledger").fetchone()[0]
        nodes = conn.execute("SELECT COUNT(*) FROM Nodes WHERE is_deleted = 0").fetchone()[0]
    assert nodes > 0            # graph was built...
    assert ledger_rows == 0     # ...without a single mechanical ledger entry


def test_agent_upserts_still_logged(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Node_Agent_Decision", "Fact_Node",
        {"description": "Chose SQLite over Postgres for local-first memory"},
        agent_name="Hermes", rationale="Local-first zero-dependency requirement",
    )
    decisions = engine.query_decision_ledger(db_path, agent_name="Hermes")
    assert len(decisions) == 1
    assert "zero-dependency" in decisions[0]["rationale"]


def test_history_capped_and_consecutive_dedupe(tmp_path):
    db_path = str(tmp_path / "test.sqlite")

    # 15 identical mechanical upserts -> history stays at 1 entry
    for _ in range(15):
        engine.get_or_create_node(
            db_path, "Node_History", "Fact_Node", {},
            agent_name="Tree-sitter", rationale="Full project AST ingestion",
        )

    def history_len():
        with engine.get_connection(db_path) as conn:
            props = json.loads(
                conn.execute("SELECT properties FROM Nodes WHERE id = 'Node_History'").fetchone()[0]
            )
            return len(props.get("history", []))

    assert history_len() == 1

    # Alternating rationales grow history but never beyond the cap (10)
    for i in range(30):
        engine.get_or_create_node(
            db_path, "Node_History", "Fact_Node", {},
            agent_name="Hermes", rationale=f"decision round {i % 2}",
        )
    assert history_len() == engine.MAX_NODE_HISTORY


def test_search_batches_access_count(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    for name in ("alpha_widget", "beta_widget", "gamma_widget"):
        engine.get_or_create_node(
            db_path, f"Node_{name}", "Fact_Node",
            {"description": f"{name} architecture note"},
            agent_name="Hermes", rationale="seed",
        )

    results = engine.search_nodes(db_path, "widget", min_trust=0.5)
    assert len(results) == 3

    with engine.get_connection(db_path) as conn:
        counts = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT id, access_count FROM Nodes WHERE id LIKE 'Node_%widget'"
            )
        }
    assert counts == {"Node_alpha_widget": 1, "Node_beta_widget": 1, "Node_gamma_widget": 1}
