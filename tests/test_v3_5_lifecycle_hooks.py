"""
v3.5.0 regression tests: harness lifecycle integration.

Covers the harness-agnostic `hook-event` dispatcher (PostToolUse auto-ingest,
Stop transcript capture + distillation, SessionStart snapshot refresh) and the
new framework hook installers (ZCode config.json event hooks, Cursor MCP +
rule, Claude Code settings.json hooks, snapshot refresh).

All HOME-resolved framework paths are monkeypatched to tmp_path so tests never
touch real harness configuration files.
"""
import json
from pathlib import Path

import graph_memory.integrations.framework_hooks as fh
from graph_memory.core import engine, lifecycle
from graph_memory.core.ingest import project_namespace


def _make_project(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (root / "main.py").write_text("import os\n\n\ndef run():\n    return os.getcwd()\n", encoding="utf-8")


def test_post_tool_use_auto_ingests(tmp_path):
    project = tmp_path / "repo"
    _make_project(project)
    db_path = str(tmp_path / "test.sqlite")

    res = lifecycle.handle_hook_event(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(project / "main.py")},
        },
        db_path=db_path,
    )
    assert res["status"] == "success"

    ns = project_namespace(project)
    with engine.get_connection(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM Nodes WHERE id = ? AND is_deleted = 0", (f"File_{ns}/main.py",)
        ).fetchone()
    assert exists is not None


def test_post_tool_use_ignores_read_tools(tmp_path):
    res = lifecycle.handle_hook_event(
        {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "/x/y.py"}},
        db_path=str(tmp_path / "unused.sqlite"),
    )
    assert res["status"] == "ignored"


def test_stop_captures_transcript_and_distills(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.sqlite")
    monkeypatch.setattr(fh, "refresh_installed_snapshots", lambda db=None: [])

    transcript = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "please fix the race condition"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "[Decision: use SQLite WAL for concurrency] fixed the race"}},
    ]
    transcript.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

    res = lifecycle.handle_hook_event(
        {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": str(transcript)},
        db_path=db_path,
    )
    assert res["turns_logged"] == 2
    assert res["facts_distilled"] >= 1

    with engine.get_connection(db_path) as conn:
        logs = conn.execute("SELECT role, content FROM Session_Logs ORDER BY id").fetchall()
        decision = conn.execute(
            "SELECT 1 FROM Nodes WHERE id LIKE 'Decision_%' AND is_deleted = 0"
        ).fetchone()
    assert [r[0] for r in logs] == ["user", "assistant"]
    assert "WAL" in logs[1][1]
    assert decision is not None


def test_zcode_hook_install_uninstall_idempotent(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)
    cfg = tmp_path / "zcode" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"model": "test-model"}), encoding="utf-8")
    monkeypatch.setattr(fh, "ZCODE_CONFIG_PATH", str(cfg))

    fh.install_hooks("zcode", db_path=db_path)
    data = json.loads(cfg.read_text())
    assert data["model"] == "test-model"  # existing config preserved
    assert data["hooks"]["enabled"] is True
    for event in ("PostToolUse", "Stop", "SessionStart"):
        assert event in data["hooks"]["events"]

    # Reinstall must not duplicate entries
    fh.install_hooks("zcode", db_path=db_path)
    data = json.loads(cfg.read_text())
    total_entries = sum(
        len(group["hooks"])
        for groups in data["hooks"]["events"].values()
        for group in groups
    )
    assert total_entries == 3

    fh.uninstall_hooks("zcode")
    data = json.loads(cfg.read_text())
    assert not data["hooks"].get("events")  # our hooks removed
    assert data["model"] == "test-model"  # user config still intact


def test_cursor_and_claude_code_install(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)
    monkeypatch.setattr(fh, "CURSOR_MCP_PATH", str(tmp_path / "cursor" / "mcp.json"))
    monkeypatch.setattr(fh, "CURSOR_RULE_FILE", str(tmp_path / "cursor" / "rules" / "gm.mdc"))
    monkeypatch.setattr(fh, "CLAUDE_SETTINGS_PATH", str(tmp_path / "claude" / "settings.json"))
    monkeypatch.setattr(fh, "CLAUDE_AUTO_FILE", str(tmp_path / "claude" / "skills" / "gm.md"))

    fh.install_hooks("cursor", db_path=db_path)
    mcp = json.loads((tmp_path / "cursor" / "mcp.json").read_text())
    assert mcp["mcpServers"]["graph-memory"]["command"] == "graph-memory-mcp"
    assert "Graph Memory Lifecycle Protocol" in (tmp_path / "cursor" / "rules" / "gm.mdc").read_text()

    fh.install_hooks("claude-code", db_path=db_path)
    settings = json.loads((tmp_path / "claude" / "settings.json").read_text())
    hooks = settings["hooks"]
    assert hooks["PostToolUse"][0]["matcher"] == "Write|Edit|MultiEdit"
    assert "Stop" in hooks and "SessionStart" in hooks

    fh.uninstall_hooks("cursor")
    assert not (tmp_path / "cursor" / "rules" / "gm.mdc").exists()
    mcp = json.loads((tmp_path / "cursor" / "mcp.json").read_text())
    assert "graph-memory" not in mcp.get("mcpServers", {})

    fh.uninstall_hooks("claude-code")
    settings = json.loads((tmp_path / "claude" / "settings.json").read_text())
    remaining = {
        event: [h for groups in hooks.get(event, []) for h in groups.get("hooks", [])]
        for event, hooks in settings.get("hooks", {}).items()
    }
    assert all(not entries for entries in remaining.values())


def test_session_start_refreshes_installed_snapshot(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.sqlite")
    auto_file = tmp_path / "claude" / "skills" / "gm.md"
    monkeypatch.setattr(fh, "CLAUDE_AUTO_FILE", str(auto_file))
    monkeypatch.setattr(fh, "CLAUDE_SETTINGS_PATH", str(tmp_path / "claude" / "settings.json"))
    monkeypatch.setattr(
        fh,
        "_REFRESHABLE",
        {"claude-code": (str(auto_file), lambda snap: fh._render_claude_code(snap))},
    )
    monkeypatch.setattr(fh, "HERMES_MEMORY_FILE", str(tmp_path / "nope" / "MEMORY.md"))

    fh.install_hooks("claude-code", db_path=db_path)
    original = auto_file.read_text()

    # New high-trust knowledge lands in the graph...
    engine.get_or_create_node(
        db_path, "Decision_wal_migration", "Fact_Node",
        {"description": "Migrated to WAL mode for multi-agent concurrency"},
        trust_score=1.0, agent_name="Hermes", rationale="Concurrency incidents",
    )

    lifecycle.handle_hook_event({"hook_event_name": "SessionStart"}, db_path=db_path)
    refreshed = auto_file.read_text()
    assert refreshed != original
    assert "WAL mode" in refreshed
