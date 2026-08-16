import os
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from graph_memory.core import engine

TEST_DB = "test_decay_ledger.sqlite"

def setup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    engine.init_db(TEST_DB)

def cleanup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

def test_effective_trust_decay():
    setup_env()
    try:
        # Create a node verified 30 days ago
        now = datetime.now(timezone.utc)
        thirty_days_ago = (now - timedelta(days=30)).isoformat()
        
        node_id = "Node_Decay_Test"
        engine.get_or_create_node(
            TEST_DB,
            node_id,
            "Fact_Node",
            {"description": "Decaying fact"},
            trust_score=1.0,
            verification_method="manual",
            agent_name="Hermes",
            rationale="Initial fact creation"
        )
        
        # Manually backdate last_verified_at to 30 days ago
        with engine.get_connection(TEST_DB) as conn:
            with engine.write_transaction(conn):
                conn.execute("UPDATE Nodes SET last_verified_at = ? WHERE id = ?", (thirty_days_ago, node_id))
                
        # Calculate effective trust (30-day half-life should yield ~0.5)
        eff_trust = engine.get_effective_trust_for_node(TEST_DB, node_id, half_life_days=30.0)
        assert abs(eff_trust - 0.5) < 0.05
        
        # Verify serialize_subgraph includes effective trust & decay info
        subgraph = engine.serialize_subgraph(TEST_DB, node_id, half_life_days=30.0)
        assert "Effective Trust:" in subgraph or "50%" in subgraph or "0.50" in subgraph
        
        # Re-verify node -> effective trust resets to 1.0
        engine.add_observation(TEST_DB, node_id, "Node is re-verified today", agent_name="Antigravity", rationale="Re-verification pass")
        eff_trust_after = engine.get_effective_trust_for_node(TEST_DB, node_id, half_life_days=30.0)
        assert eff_trust_after > 0.95
    finally:
        cleanup_env()

def test_global_decision_ledger():
    setup_env()
    try:
        engine.get_or_create_node(
            TEST_DB,
            "Node_1",
            "Fact_Node",
            {"title": "First"},
            agent_name="Hermes",
            rationale="Created first node for architecture"
        )
        
        engine.get_or_create_node(
            TEST_DB,
            "Node_2",
            "Fact_Node",
            {"title": "Second"},
            agent_name="Hermes",
            rationale="Created second node for security"
        )
        
        engine.add_observation(
            TEST_DB,
            "Node_1",
            "Added observation",
            agent_name="Antigravity",
            rationale="Refactored observation logic"
        )
        
        # Query global decision ledger for Hermes
        hermes_decisions = engine.query_decision_ledger(TEST_DB, agent_name="Hermes")
        assert len(hermes_decisions) >= 2
        assert any("architecture" in d["rationale"] for d in hermes_decisions)
        
        # Query global decision ledger for Antigravity
        ag_decisions = engine.query_decision_ledger(TEST_DB, agent_name="Antigravity")
        assert len(ag_decisions) >= 1
        assert "Refactored observation logic" in ag_decisions[0]["rationale"]
    finally:
        cleanup_env()

if __name__ == "__main__":
    test_effective_trust_decay()
    test_global_decision_ledger()
    print("✅ All v2.1.0 decay & ledger unit tests passed!")
