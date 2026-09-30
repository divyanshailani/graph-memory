"""
v3.9.0 regression tests: test-driven re-verification and the scheduled cron.

1. reverify_test_backed_nodes restores trust ONLY on curated nodes (knowledge,
   release, episode) when the suite is green; AST-derived nodes (File,
   Component, Dependency, MOC, Project) are never touched, and a red run
   re-verifies nothing.
2. scheduler.verify_argv points the OS job at the right db with --tests.
"""
from graph_memory.core import engine
from graph_memory.integrations import scheduler


def _seed(db):
    """One curated Knowledge_Node and one AST File node, both decayed."""
    engine.get_or_create_node(
        db, "K1", "Knowledge_Node", {"description": "release sequencing decision"},
        trust_score=0.3, verification_method="manual",
    )
    engine.get_or_create_node(
        db, f"File_ns/x.py", "Fact_Node",
        {"entity_type": "File", "path": "x.py", "file_hash": "deadbeef"},
        trust_score=0.3, verification_method="source_parse",
    )


def test_green_suite_bumps_curated_only(tmp_path):
    db = str(tmp_path / "g.sqlite")
    _seed(db)
    stats = engine.reverify_test_backed_nodes(db, workspace_dir=str(tmp_path), test_cmd="true")
    assert stats["passed"] and stats["nodes_reverified"] == 1
    with engine.get_connection(db) as conn:
        k = conn.execute("SELECT trust_score, verification_method FROM Nodes WHERE id='K1'").fetchone()
        f = conn.execute("SELECT trust_score, verification_method FROM Nodes WHERE id='File_ns/x.py'").fetchone()
    assert k == (1.0, "test_pass")
    assert f == (0.3, "source_parse")  # AST node untouched: a green suite proves nothing about hashes


def test_red_suite_bumps_nothing(tmp_path):
    db = str(tmp_path / "g.sqlite")
    _seed(db)
    stats = engine.reverify_test_backed_nodes(db, workspace_dir=str(tmp_path), test_cmd="false")
    assert not stats["passed"] and stats["nodes_reverified"] == 0
    with engine.get_connection(db) as conn:
        trust = conn.execute("SELECT trust_score FROM Nodes WHERE id='K1'").fetchone()[0]
    assert trust == 0.3


def test_cron_argv_targets_db_with_tests(tmp_path):
    db = str(tmp_path / ".agents" / "graph_memory.sqlite")
    argv = scheduler.verify_argv(db, tests=True)
    assert any("verify" in a for a in argv)
    assert "--tests" in argv
    assert any(db in a or "graph_memory.sqlite" in a for a in argv)
