"""
v3.8.3 regression tests.

1. Snapshot visibility — the candidate pool used to be an ID-ordered `LIMIT 50`
   window, so with more than 50 nodes the snapshot only ever saw the alphabetically
   first IDs: knowledge cards and release milestones could never appear no matter
   how trusted they were.
2. Hash-stable re-verification — AST facts whose source file is byte-identical to
   the hash recorded at ingest are re-verified mechanically (trust back to 1.0)
   without an agent, so an idle graph cannot decay out of its own memory. Changed
   files, missing files and curated (file-less) nodes are left alone, and no
   Decision_Ledger rows are written.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from graph_memory.core import engine
from graph_memory.core.snapshot import generate_active_snapshot


def _aged_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_snapshot_surfaces_milestones_past_alphabetical_window(tmp_path):
    """A release node that sorts after hundreds of dependency nodes must still be
    injected — the old window returned only the first 50 IDs alphabetically."""
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)

    for i in range(120):
        engine.get_or_create_node(
            db_path, f"Dependency_aaaa_{i:03d}", "Fact_Node",
            {"description": f"ambient fact {i}"},
            trust_score=0.8, verification_method="source_parse",
        )

    engine.get_or_create_node(
        db_path, "Knowledge_trust_decay_model", "Knowledge_Node",
        {"description": "Effective trust = base x 0.5^(days/half_life)"},
        trust_score=1.0, verification_method="manual",
    )
    engine.get_or_create_node(
        db_path, "Release_v9_9_9", "Release_Node",
        {"version": "9.9.9", "changes": ["first change", "second change"]},
        trust_score=1.0, verification_method="manual",
    )

    engine.get_or_create_node(
        db_path, "File_no_desc.py", "Fact_Node",
        {"entity_type": "File", "path": "no_desc.py"},
        trust_score=1.0, verification_method="source_parse",
    )

    snap = generate_active_snapshot(db_path, max_tokens=4000, min_trust=0.5)
    assert "## Project Milestones & Releases" in snap
    assert "[Release_v9_9_9]" in snap
    assert "[Knowledge_trust_decay_model]" in snap
    assert "first change" in snap  # list-valued `changes` rendered as text, not repr
    assert "[File_no_desc.py]" not in snap  # nothing but an ID — not worth injection budget


def test_reverify_refreshes_only_hash_stable_files(tmp_path):
    project = tmp_path / "repo"
    project.mkdir()
    stable, changed, gone = project / "stable.py", project / "changed.py", project / "gone.py"
    stable.write_text("def a():\n    return 1\n", encoding="utf-8")
    changed.write_text("def b():\n    return 2\n", encoding="utf-8")

    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)

    def register(file_node_id, rel_path, abs_path, payload):
        engine.get_or_create_node(
            db_path, file_node_id, "Fact_Node",
            {
                "entity_type": "File",
                "path": rel_path,
                "abs_path": str(abs_path),
                "file_hash": hashlib.sha256(payload).hexdigest(),
            },
            trust_score=1.0, verification_method="source_parse",
        )
        engine.get_or_create_node(
            db_path, f"Func_{rel_path}", "Fact_Node",
            {"entity_type": "Component", "file_path": rel_path, "name": "a"},
            trust_score=1.0, verification_method="source_parse",
        )

    register("File_stable.py", "stable.py", stable, stable.read_bytes())
    register("File_changed.py", "changed.py", changed, changed.read_bytes())
    register("File_gone.py", "gone.py", gone, b"def c():\n    return 3\n")
    engine.get_or_create_node(
        db_path, "Knowledge_hand_written", "Knowledge_Node",
        {"description": "no file backs this fact"},
        trust_score=1.0, verification_method="manual",
    )

    # Derived nodes that own no file: verified only via their inbound evidence.
    for node_id, entity_type in (
        ("Dependency_stable_import", "External_Dependency"),
        ("Dependency_changed_import", "External_Dependency"),
        ("MOC_dir", "MOC_Hub"),
        ("MOC_stable", "MOC_Hub"),
        ("Project_root", "Project"),
    ):
        engine.get_or_create_node(
            db_path, node_id, "Fact_Node", {"entity_type": entity_type},
            trust_score=1.0, verification_method="source_parse",
        )
    engine.create_relation(db_path, "Func_stable.py", "Dependency_stable_import", "IMPORTS")
    engine.create_relation(db_path, "Func_changed.py", "Dependency_changed_import", "IMPORTS")
    engine.create_relation(db_path, "File_stable.py", "MOC_dir", "CONTAINS")
    engine.create_relation(db_path, "File_changed.py", "MOC_dir", "CONTAINS")
    engine.create_relation(db_path, "File_stable.py", "MOC_stable", "CONTAINS")
    engine.create_relation(db_path, "MOC_dir", "Project_root", "PART_OF")
    engine.create_relation(db_path, "MOC_stable", "Project_root", "PART_OF")
    # An agent assertion attached to the root is not derivation evidence.
    engine.create_relation(db_path, "Knowledge_hand_written", "Project_root", "PART_OF")

    # Everything above is 90 days unverified: deep in decay.
    with engine.get_connection(db_path) as conn:
        with engine.write_transaction(conn):
            conn.execute("UPDATE Nodes SET last_verified_at = ?", (_aged_iso(90),))
    assert engine.get_effective_trust_for_node(db_path, "Func_stable.py") < 0.2

    changed.write_text("def b():\n    return 3  # edited after ingest\n", encoding="utf-8")

    with engine.get_connection(db_path) as conn:
        ledger_before = conn.execute("SELECT COUNT(*) FROM Decision_Ledger").fetchone()[0]

    stats = engine.reverify_hash_stable_nodes(db_path)
    assert stats["files_checked"] == 3
    assert stats["files_stable"] == 1
    assert stats["files_changed"] == 1
    assert stats["files_missing"] == 1
    assert stats["nodes_propagated"] == 2  # Dependency_stable_import + MOC_stable

    # Unchanged source: the derived fact is still true, so it is fresh again.
    assert engine.get_effective_trust_for_node(db_path, "Func_stable.py") > 0.95
    assert engine.get_effective_trust_for_node(db_path, "File_stable.py") > 0.95
    # Edited source: the ingester owns it, not this pass.
    assert engine.get_effective_trust_for_node(db_path, "Func_changed.py") < 0.2
    # Missing source and curated nodes are never mechanically verified.
    assert engine.get_effective_trust_for_node(db_path, "Func_gone.py") < 0.2
    assert engine.get_effective_trust_for_node(db_path, "Knowledge_hand_written") < 0.2

    # Evidence propagation: a file-less derived node is fresh only when every derived
    # input feeding it is fresh.
    assert engine.get_effective_trust_for_node(db_path, "Dependency_stable_import") > 0.95
    assert engine.get_effective_trust_for_node(db_path, "MOC_stable") > 0.95
    assert engine.get_effective_trust_for_node(db_path, "Dependency_changed_import") < 0.2
    assert engine.get_effective_trust_for_node(db_path, "MOC_dir") < 0.2
    assert engine.get_effective_trust_for_node(db_path, "Project_root") < 0.2

    # Mechanical re-verification is not an agent decision — the audit trail stays clean.
    with engine.get_connection(db_path) as conn:
        ledger_after = conn.execute("SELECT COUNT(*) FROM Decision_Ledger").fetchone()[0]
    assert ledger_after == ledger_before
