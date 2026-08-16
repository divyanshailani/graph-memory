"""
v3.5.1 regression tests: Living Memory quick wins.

1. Hash-skip incremental ingestion — unchanged files skip parsing and upserts,
   and a fully-unchanged re-ingestion never even loads a tree-sitter parser.
2. Prompt-stable snapshots — deterministic ordering plus a content-fingerprint
   cache: an unchanged graph returns byte-identical snapshot text.
3. sweep_orphans protects every Project_* root from being swept.
"""
from pathlib import Path

from graph_memory.core import engine
from graph_memory.core.ingest import ingest_codebase, ingest_file, project_namespace
from graph_memory.core.snapshot import generate_active_snapshot


def _make_project(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (root / "main.py").write_text("import os\n\n\ndef run():\n    return os.getcwd()\n", encoding="utf-8")
    (root / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")


def test_hash_skip_on_reingestion(tmp_path):
    project = tmp_path / "repo"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")

    first = ingest_codebase(db_path, str(project))
    assert first["parsed"] >= 2
    assert first["skipped"] == 0

    ns = project_namespace(project)
    with engine.get_connection(db_path) as conn:
        updated_before = conn.execute(
            "SELECT updated_at FROM Nodes WHERE id = ?", (f"File_{ns}/main.py",)
        ).fetchone()[0]

    second = ingest_codebase(db_path, str(project))
    assert second["parsed"] == 0
    assert second["skipped"] == first["parsed"]

    with engine.get_connection(db_path) as conn:
        updated_after = conn.execute(
            "SELECT updated_at FROM Nodes WHERE id = ?", (f"File_{ns}/main.py",)
        ).fetchone()[0]
    assert updated_after == updated_before  # zero writes for unchanged files


def test_ingest_file_unchanged_status(tmp_path):
    project = tmp_path / "repo"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")
    target = project / "main.py"

    first = ingest_file(db_path, str(target))
    assert first["status"] == "success"
    second = ingest_file(db_path, str(target))
    assert second["status"] == "unchanged"

    (project / "main.py").write_text(
        "import os\n\n\ndef run():\n    return os.getcwd()\n\n\ndef extra():\n    pass\n",
        encoding="utf-8",
    )
    third = ingest_file(db_path, str(target))
    assert third["status"] == "success"


def test_snapshot_prompt_stability(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Fact_Zeta", "Fact_Node", {"description": "Zebra fact"},
        trust_score=1.0, agent_name="Hermes", rationale="seed z",
    )
    engine.get_or_create_node(
        db_path, "Fact_Alpha", "Fact_Node", {"description": "Alpha fact"},
        trust_score=1.0, agent_name="Hermes", rationale="seed a",
    )

    snap1 = generate_active_snapshot(db_path, max_tokens=500, min_trust=0.5)
    snap2 = generate_active_snapshot(db_path, max_tokens=500, min_trust=0.5)
    assert snap1 == snap2  # byte-identical on unchanged graph

    # Deterministic ordering: Alpha before Zeta regardless of creation order.
    assert snap1.index("Fact_Alpha") < snap1.index("Fact_Zeta")

    engine.get_or_create_node(
        db_path, "Fact_New", "Fact_Node", {"description": "Freshly learned fact"},
        trust_score=1.0, agent_name="Hermes", rationale="new knowledge",
    )
    snap3 = generate_active_snapshot(db_path, max_tokens=500, min_trust=0.5)
    assert snap3 != snap1
    assert "Fact_New" in snap3


def test_sweep_protects_project_roots(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Project_SomeRepo_abc123", "Fact_Node",
        {"entity_type": "Project", "path": "/tmp/SomeRepo"},
        agent_name="Tree-sitter", rationale="root",
    )
    engine.get_or_create_node(
        db_path, "Node_Legit", "Fact_Node", {"description": "has edges"},
        link_to="Project_SomeRepo_abc123", agent_name="Hermes", rationale="linked",
    )
    engine.get_or_create_node(
        db_path, "Node_TrueOrphan", "Fact_Node", {"description": "no edges"},
        agent_name="Hermes", rationale="orphan",
    )

    swept = engine.sweep_orphans(db_path)

    assert swept == 1  # only the true orphan
    with engine.get_connection(db_path) as conn:
        root = conn.execute(
            "SELECT is_deleted FROM Nodes WHERE id = 'Project_SomeRepo_abc123'"
        ).fetchone()
        orphan = conn.execute(
            "SELECT is_deleted FROM Nodes WHERE id = 'Node_TrueOrphan'"
        ).fetchone()
    assert root[0] == 0      # edge-less Project root survives
    assert orphan[0] == 1
