"""
v3.7.0 regression tests: Scale & Teams.

1. bulk_upsert_nodes — one-transaction batch upserts with get_or_create
   semantics (history cap, trust MAX, no ledger rows).
2. Cross-file CALLS resolution — stubs repointed to unique same-namespace
   definitions; ambiguous names keep their stubs; edge-less stubs removed.
3. Trigram identifier search — 'effective_tr' style fragments find nodes the
   unicode61 tokenizer can't.
4. Contradiction detection — agent-driven overwrites record conflicts and
   surface in detect_contradictions; mechanical AST upserts never do.
5. prune GC — stale, decayed, unreferenced nodes are soft-deleted; fresh,
   referenced, and Project-root nodes survive.
6. Reflection engine — memory cards contain real Decision_Ledger digests.
"""
import json
from pathlib import Path

from graph_memory.core import engine
from graph_memory.core.ingest import ingest_codebase, project_namespace
from graph_memory.core.memory import reflect_session_memory


def test_bulk_upsert_semantics(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    nodes = [
        {"id": "N_A", "label": "Fact_Node", "properties": {"description": "alpha"}, "trust_score": 0.9, "verification_method": "import"},
        {"id": "N_B", "label": "Fact_Node", "properties": {"description": "beta"}, "trust_score": 0.9, "verification_method": "import"},
    ]
    edges = [{"source_id": "N_A", "target_id": "N_B", "relation_type": "AFFECTS"}]

    engine.bulk_upsert_nodes(db_path, nodes, edges, agent_name="Bulk", rationale="batch")
    engine.bulk_upsert_nodes(db_path, nodes, edges, agent_name="Bulk", rationale="batch")  # idempotent

    with engine.get_connection(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM Nodes").fetchone()[0]
        ledger = conn.execute("SELECT COUNT(*) FROM Decision_Ledger").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM Edges").fetchone()[0]
        trust = conn.execute("SELECT trust_score FROM Nodes WHERE id='N_A'").fetchone()[0]

    assert count == 2 and edge_count == 1
    assert ledger == 0          # mechanical batch — no audit noise
    assert trust == 0.9


def test_cross_file_call_resolution(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (project / "a.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (project / "b.py").write_text("from a import helper\n\n\ndef run():\n    return helper()\n", encoding="utf-8")
    db_path = str(tmp_path / "test.sqlite")

    res = ingest_codebase(db_path, str(project))
    assert res["calls_resolved"] >= 1

    ns = project_namespace(project)
    with engine.get_connection(db_path) as conn:
        edge = conn.execute(
            "SELECT 1 FROM Edges WHERE source_id = ? AND target_id = ? AND relation_type = 'CALLS'",
            (f"Func_run_{ns}/b.py", f"Func_helper_{ns}/a.py"),
        ).fetchone()
        stub_left = conn.execute(
            "SELECT 1 FROM Nodes WHERE id = ?", (f"Func_helper_{ns}/b.py",)
        ).fetchone()
    assert edge is not None      # call graph crosses the file boundary
    assert stub_left is None     # edge-less stub cleaned up


def test_trigram_identifier_search(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Func_calculate_effective_trust_x.py", "Fact_Node",
        {"description": "computes decayed trust"},
        agent_name="Hermes", rationale="seed",
    )
    # Partial identifier with underscore: unicode61 tokenizes to nothing useful.
    results = engine.search_nodes(db_path, "effective_tr", min_trust=0.0)
    assert any(r["id"] == "Func_calculate_effective_trust_x.py" for r in results)
    # Longer fragment narrows to the same node.
    results2 = engine.search_nodes(db_path, "calculate_effective", min_trust=0.0)
    assert any(r["id"] == "Func_calculate_effective_trust_x.py" for r in results2)


def test_contradiction_detection(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Decision_db_engine", "Fact_Node",
        {"description": "Use Postgres for storage"},
        agent_name="Hermes", rationale="initial choice",
    )
    engine.get_or_create_node(  # different agent, different assertion
        db_path, "Decision_db_engine", "Fact_Node",
        {"description": "Use SQLite WAL for storage"},
        agent_name="Antigravity", rationale="local-first requirement",
    )

    conflicts = engine.detect_contradictions(db_path)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["node_id"] == "Decision_db_engine"
    assert c["conflicts"][0]["old"] == "Use Postgres for storage"
    assert c["conflicts"][0]["new"] == "Use SQLite WAL for storage"

    # Mechanical upserts (log_ledger=False) must never record conflicts.
    engine.get_or_create_node(
        db_path, "Decision_db_engine", "Fact_Node",
        {"description": "Use DuckDB for analytics"},
        agent_name="Tree-sitter", rationale="reparse", log_ledger=False,
    )
    conflicts2 = engine.detect_contradictions(db_path)
    assert len(conflicts2[0]["conflicts"]) == 1  # unchanged


def test_prune_stale_nodes(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Project_X_a1", "Fact_Node", {"entity_type": "Project"},
        agent_name="Hermes", rationale="root",
    )
    engine.get_or_create_node(
        db_path, "Node_Fresh", "Fact_Node", {"description": "recent"},
        agent_name="Hermes", rationale="fresh",
    )
    engine.get_or_create_node(
        db_path, "Node_Stale", "Fact_Node", {"description": "ancient"},
        agent_name="Hermes", rationale="stale",
    )
    with engine.get_connection(db_path) as conn:
        with engine.write_transaction(conn):
            conn.execute(
                "UPDATE Nodes SET last_verified_at = datetime('now', '-120 days') WHERE id = 'Node_Stale'"
            )

    pruned = engine.prune_stale_nodes(db_path, days=45, min_trust=0.2)
    assert pruned == 1

    with engine.get_connection(db_path) as conn:
        states = dict(conn.execute("SELECT id, is_deleted FROM Nodes").fetchall())
    assert states["Node_Stale"] == 1
    assert states["Node_Fresh"] == 0
    assert states["Project_X_a1"] == 0  # roots never pruned


def test_trigram_upgrade_path_no_corruption(tmp_path):
    """Regression: identifier search must work on any pre-existing database with
    zero auxiliary-index corruption surface. (An external-content trigram FTS5
    table with sync triggers intermittently raised 'database disk image is
    malformed' under WAL; identifier search now uses a LIKE substring fallback
    with no extra index to corrupt.)"""
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Func_legacy_symbol_x.py", "Fact_Node",
        {"description": "pre-index node"},
        agent_name="Hermes", rationale="seed",
    )

    # Repeated trigger-driven updates (previously the corruption vector) must succeed.
    for i in range(5):
        engine.get_or_create_node(
            db_path, "Func_legacy_symbol_x.py", "Fact_Node",
            {"description": f"refreshed {i}"},
            agent_name="Hermes", rationale="re-verify",
        )

    results = engine.search_nodes(db_path, "legacy_sym", min_trust=0.0)
    assert any(r["id"] == "Func_legacy_symbol_x.py" for r in results)


def test_reflection_uses_real_ledger(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Decision_wal_fix", "Fact_Node",
        {"description": "Fixed database locked errors"},
        agent_name="Hermes", rationale="fixed locking bug with WAL mode",
    )
    engine.get_or_create_node(
        db_path, "Decision_http", "Fact_Node",
        {"description": "Added MCP HTTP transport"},
        agent_name="Antigravity", rationale="added streamable HTTP transport to MCP server",
    )

    res = reflect_session_memory(db_path, str(tmp_path / "out"))
    assert res["status"] == "success"
    assert res["decisions_reflected"] >= 2

    pitfalls = (tmp_path / "out" / "memories" / "common_pitfalls_experience" / "common_pitfalls_experience.md").read_text()
    assert "locking bug" in pitfalls  # real rationale, not static boilerplate
    tech = (tmp_path / "out" / "memories" / "project_tech_stack" / "project_tech_stack.md").read_text()
    assert "HTTP transport" in tech
