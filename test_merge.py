import os
import sqlite3
import json
from graph_memory.core import engine

TEST_DB = "test_merge.sqlite"

def setup_db():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    engine.init_db(TEST_DB)

def cleanup_db():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

def test_basic_merge():
    setup_db()
    try:
        # Create Node_A and Node_B
        engine.get_or_create_node(TEST_DB, "Node_A", "Fact_Node", {"observations": ["A is alive"], "type": "Fact_Node"})
        engine.get_or_create_node(TEST_DB, "Node_B", "Fact_Node", {"observations": ["B is running"], "type": "Fact_Node"})

        # Merge Node_A into Node_B
        res = engine.merge_nodes(TEST_DB, "Node_A", "Node_B")
        assert res["status"] == "success"

        # Verify Node_B has merged properties and aliases
        subgraph = engine.serialize_subgraph(TEST_DB, "Node_B")
        assert "A is alive" in subgraph
        assert "B is running" in subgraph

        # Verify Node_A redirects to Node_B
        subgraph_a = engine.serialize_subgraph(TEST_DB, "Node_A")
        print("DEBUG SUBGRAPH A:", repr(subgraph_a))
        assert "[Alias Redirect:" in subgraph_a
        assert "Node_B" in subgraph_a
    finally:
        cleanup_db()

def test_edge_constraint_and_self_loop():
    setup_db()
    try:
        # Setup nodes
        engine.get_or_create_node(TEST_DB, "Node_X", "Fact_Node")
        engine.get_or_create_node(TEST_DB, "Node_Y", "Fact_Node")
        engine.get_or_create_node(TEST_DB, "Lib_Z", "Fact_Node")

        # Edge from X to Lib_Z AND Y to Lib_Z (Potential constraint collision upon merge)
        engine.create_relation(TEST_DB, "Node_X", "Lib_Z", "USES")
        engine.create_relation(TEST_DB, "Node_Y", "Lib_Z", "USES")

        # Edge between X and Y (Potential self-loop upon merge)
        engine.create_relation(TEST_DB, "Node_X", "Node_Y", "DEPENDS_ON")

        # Merge X into Y
        res = engine.merge_nodes(TEST_DB, "Node_X", "Node_Y")
        assert res["status"] == "success"

        # Verify no SQLite crash and no self-loops on Node_Y
        graph = engine.read_graph(TEST_DB)
        edges = graph["edges"]
        
        # Verify no self-loops (source_id == target_id)
        for e in edges:
            assert e["source_id"] != e["target_id"]

        # Verify Node_Y -[USES]-> Lib_Z exists exactly once
        uses_edges = [e for e in edges if e["source_id"] == "Node_Y" and e["target_id"] == "Lib_Z"]
        assert len(uses_edges) == 1
    finally:
        cleanup_db()

def test_cascading_alias_redirect():
    setup_db()
    try:
        engine.get_or_create_node(TEST_DB, "Node_Alpha", "Fact_Node")
        engine.get_or_create_node(TEST_DB, "Node_Beta", "Fact_Node")
        engine.get_or_create_node(TEST_DB, "Node_Gamma", "Fact_Node")

        # Merge Alpha -> Beta, then Beta -> Gamma
        engine.merge_nodes(TEST_DB, "Node_Alpha", "Node_Beta")
        engine.merge_nodes(TEST_DB, "Node_Beta", "Node_Gamma")

        # Resolving Alpha should chain to Gamma
        canonical = engine.resolve_canonical_id(TEST_DB, "Node_Alpha")
        assert canonical == "Node_Gamma"

        subgraph = engine.serialize_subgraph(TEST_DB, "Node_Alpha")
        assert "[Alias Redirect:" in subgraph
        assert "Node_Gamma" in subgraph
    finally:
        cleanup_db()

if __name__ == "__main__":
    test_basic_merge()
    test_edge_constraint_and_self_loop()
    test_cascading_alias_redirect()
    print("✅ All merge unit tests passed!")
