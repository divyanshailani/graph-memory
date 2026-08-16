"""
v3.6.0 regression tests: Open Borders.

1. Markdown memory importer (CLAUDE.md / .cursorrules / any .md) — sections
   become Knowledge_Nodes with bullet observations; idempotent on re-import.
2. mem0 JSON importer — memory records become Fact_Nodes with stable IDs.
3. Obsidian vault export — curated notes with [[wikilinks]] for graph edges;
   mechanical AST nodes are excluded.
4. `--root` namespace pinning — ingest-code and ingest-file derive identical
   IDs in monorepo layouts regardless of nested project markers.
5. HTTP MCP transport — the app builds and mounts /mcp + /health.
"""
import json
from pathlib import Path

import pytest

from graph_memory.core import engine
from graph_memory.core.importers import import_markdown_file, import_mem0
from graph_memory.core.ingest import ingest_codebase, ingest_file, project_namespace
from graph_memory.core.obsidian import export_obsidian_vault

CLAUDE_MD = """# Project Memory

## Architecture

- Uses SQLite WAL for multi-agent concurrency
- Trust decay with 30-day half-life

## Build

- Run pytest before every release
"""


def test_import_markdown_claude_md(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(CLAUDE_MD, encoding="utf-8")

    res = import_markdown_file(db_path, str(claude_md))
    assert res["status"] == "success"
    assert res["sections_imported"] >= 2

    # Idempotent: re-import does not create duplicates
    import_markdown_file(db_path, str(claude_md))
    with engine.get_connection(db_path) as conn:
        section_count = conn.execute(
            "SELECT COUNT(*) FROM Nodes WHERE id LIKE 'Import_MD_CLAUDE_%' AND is_deleted = 0"
        ).fetchone()[0]
        props = json.loads(
            conn.execute(
                "SELECT properties FROM Nodes WHERE id = 'Import_MD_CLAUDE_Architecture'"
            ).fetchone()[0]
        )
    assert section_count == 2
    assert props["source"] == "claude_md_import"
    assert any("SQLite WAL" in o for o in props["observations"])


def test_import_mem0(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    export = tmp_path / "mem0.json"
    export.write_text(
        json.dumps(
            {
                "results": [
                    {"id": "m1", "memory": "User prefers uv over pip"},
                    {"id": "m2", "memory": "Deployments go through GoRouter"},
                    "legacy bare-string memory",  # older mem0 export format, still imported
                ]
            }
        ),
        encoding="utf-8",
    )

    res = import_mem0(db_path, str(export))
    assert res["status"] == "success"
    assert res["memories_imported"] == 3  # bare-string records are supported

    with engine.get_connection(db_path) as conn:
        m1 = conn.execute(
            "SELECT properties FROM Nodes WHERE id = 'Import_Mem0_m1' AND is_deleted = 0"
        ).fetchone()
        bare = conn.execute(
            "SELECT COUNT(*) FROM Nodes WHERE id LIKE 'Import_Mem0_legacy_bare%' AND is_deleted = 0"
        ).fetchone()[0]
    assert m1 is not None
    assert "uv over pip" in m1[0]
    assert bare == 1


def test_export_obsidian(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.get_or_create_node(
        db_path, "Decision_wal", "Fact_Node", {"description": "Use WAL mode"},
        agent_name="Hermes", rationale="concurrency",
    )
    engine.get_or_create_node(
        db_path, "Decision_fts", "Fact_Node", {"description": "Use FTS5"},
        agent_name="Hermes", rationale="search speed",
    )
    engine.create_relation(db_path, "Decision_wal", "Decision_fts", "AFFECTS")
    # Mechanical AST node must be excluded from the vault
    engine.get_or_create_node(
        db_path, "File_x/a.py", "Fact_Node", {"entity_type": "File", "path": "a.py"},
        agent_name="Tree-sitter", rationale="ingest",
    )

    vault = tmp_path / "vault"
    res = export_obsidian_vault(db_path, str(vault))
    assert res["notes_written"] == 2
    assert res["links_written"] >= 2  # one outgoing + one incoming rendering

    wal_note = (vault / "Decision_wal.md").read_text(encoding="utf-8")
    assert "[[Decision_fts]]" in wal_note
    assert "Use WAL mode" in wal_note
    assert not (vault / "File_x_a.py.md").exists()


def test_root_flag_namespace_parity(tmp_path):
    monorepo = tmp_path / "monorepo"
    pkg = monorepo / "packages" / "app"
    pkg.mkdir(parents=True)
    # Nested marker would normally capture the namespace to packages/app
    (pkg / "package.json").write_text('{"name":"app"}', encoding="utf-8")
    (pkg / "main.py").write_text("def run():\n    pass\n", encoding="utf-8")
    db_path = str(tmp_path / "test.sqlite")

    ingest_codebase(db_path, str(pkg), root=str(monorepo))
    ns = project_namespace(monorepo)
    expected_id = f"File_{ns}/packages/app/main.py"

    with engine.get_connection(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM Nodes WHERE id = ? AND is_deleted = 0", (expected_id,)
        ).fetchone()
    assert exists is not None

    # ingest_file with the same --root resolves to the SAME node, not a duplicate
    ingest_file(db_path, str(pkg / "main.py"), root=str(monorepo))
    with engine.get_connection(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM Nodes WHERE id = ?", (expected_id,)
        ).fetchone()[0]
    assert count == 1


def test_http_app_builds():
    pytest.importorskip("starlette")
    from graph_memory.mcp.http_server import create_http_app

    app = create_http_app()
    route_paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in route_paths
    assert "/mcp" in route_paths
