import os
import pytest
from graph_memory.core import engine
from graph_memory.core.snapshot import generate_active_snapshot
from graph_memory.core.distill import distill_session_exchanges

TEST_DB = "test_v3_snapshot.sqlite"

def setup_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    engine.init_db(TEST_DB)

def teardown_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_snapshot_generation():
    setup_env()
    try:
        engine.get_or_create_node(TEST_DB, "Fact_Test_1", "Fact_Node", {"description": "Graph memory supports dynamic decay"}, trust_score=1.0)
        engine.get_or_create_node(TEST_DB, "Episode_v3", "Episode_Node", {"description": "v3.0.0 Hermes memory integration"}, trust_score=1.0)

        snap = generate_active_snapshot(TEST_DB, max_tokens=500, min_trust=0.5)
        assert "Epistemic Graph Memory Snapshot" in snap
        assert "Fact_Test_1" in snap
        assert "Episode_v3" in snap
    finally:
        teardown_env()

def test_session_logging_and_distillation():
    setup_env()
    try:
        exchanges = [
            {"role": "user", "content": "Please deploy v3.0.0 and fix tree-sitter parser compatibility."},
            {"role": "assistant", "content": "[Fact: tree_sitter_v021_compatibility] Implemented multi-tier fallback for tree-sitter v0.21+ packages."}
        ]

        res = distill_session_exchanges(TEST_DB, "session_101", "Hermes_Agent", exchanges)
        assert res["distilled_facts_count"] >= 1
        assert "Fact_tree_sitter_v021_compatibility" in res["nodes_updated"]

        # Search session logs using FTS5
        logs = engine.search_session_logs(TEST_DB, "tree-sitter")
        assert len(logs) >= 1
        assert logs[0]["role"] in ("user", "assistant")
    finally:
        teardown_env()
