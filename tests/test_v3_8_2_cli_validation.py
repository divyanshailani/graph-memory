"""Tests for v3.8.2: __version__ exposure, --version flag, and add_node input validation."""

import json
import subprocess
import sys

from graph_memory import __version__
from graph_memory.core import engine


def _run_cli(*argv):
    return subprocess.run(
        [sys.executable, "-m", "graph_memory.cli", *argv],
        capture_output=True, text=True,
    )


def test_dunder_version_matches_pyproject():
    # regex instead of tomllib: tomllib is 3.11+ and this project supports 3.10
    import re
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.M).group(1)
    assert __version__ == declared


def test_version_flag():
    result = _run_cli("--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"graph-memory {__version__}"


def test_add_node_valid(tmp_path):
    db = str(tmp_path / "test.sqlite")
    engine.init_db(db)
    result = _run_cli("--db", db, "add_node", "MyNode", "Fact_Node", '{"type": "note"}')
    assert result.returncode == 0, result.stderr
    assert "added/updated successfully" in result.stdout
    node = engine.get_node(db, "MyNode") if hasattr(engine, "get_node") else None
    # verify via search regardless of helper availability
    hits = engine.search_nodes(db, "MyNode", min_trust=0.0)
    assert any(h["id"] == "MyNode" for h in hits)


def test_add_node_rejects_empty_node_id(tmp_path):
    db = str(tmp_path / "test.sqlite")
    engine.init_db(db)
    result = _run_cli("--db", db, "add_node", "   ", "Fact_Node")
    assert result.returncode != 0
    assert "node_id" in result.stderr
    # nothing was created
    assert engine.search_nodes(db, "Fact_Node", min_trust=0.0) == []


def test_add_node_rejects_empty_label(tmp_path):
    db = str(tmp_path / "test.sqlite")
    engine.init_db(db)
    result = _run_cli("--db", db, "add_node", "MyNode", "")
    assert result.returncode != 0
    assert "label" in result.stderr


def test_add_node_rejects_non_json_properties(tmp_path):
    db = str(tmp_path / "test.sqlite")
    engine.init_db(db)
    result = _run_cli("--db", db, "add_node", "MyNode", "Fact_Node", "{not json")
    assert result.returncode != 0
    assert "valid JSON" in result.stderr


def test_add_node_rejects_non_object_properties(tmp_path):
    db = str(tmp_path / "test.sqlite")
    engine.init_db(db)
    result = _run_cli("--db", db, "add_node", "MyNode", "Fact_Node", '["array", "not", "object"]')
    assert result.returncode != 0
    assert "JSON object" in result.stderr
