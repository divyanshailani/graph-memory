import os
from datetime import datetime, timezone, timedelta
from graph_memory.core import engine

TEST_DB = "test_v2_1_1_fixes.sqlite"

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

def test_timedelta_import_fix():
    setup_env()
    try:
        engine.get_or_create_node(
            TEST_DB,
            "Node_History_Test",
            "Fact_Node",
            {"description": "Testing timedelta import"},
            agent_name="Hermes",
            rationale="Testing days query"
        )
        
        # This will raise NameError if timedelta is missing at top level
        decisions = engine.query_decision_ledger(TEST_DB, days=7)
        assert len(decisions) >= 1
    finally:
        cleanup_env()

def test_effective_trust_search_filtering():
    setup_env()
    try:
        now = datetime.now(timezone.utc)
        # Create a fresh node (0 days old) with trust 1.0
        engine.get_or_create_node(
            TEST_DB,
            "Fresh_Node",
            "Fact_Node",
            {"description": "Fresh architecture documentation"},
            trust_score=1.0,
            agent_name="Antigravity",
            rationale="Fresh node"
        )
        
        # Create a stale node (300 days old) with baseline trust 1.0 -> decays to ~0.001
        stale_id = "Stale_Node"
        engine.get_or_create_node(
            TEST_DB,
            stale_id,
            "Fact_Node",
            {"description": "Stale architecture documentation"},
            trust_score=1.0,
            agent_name="Antigravity",
            rationale="Stale node"
        )
        
        # Backdate Stale_Node last_verified_at to 300 days ago
        stale_time = (now - timedelta(days=300)).isoformat()
        with engine.get_connection(TEST_DB) as conn:
            with engine.write_transaction(conn):
                conn.execute("UPDATE Nodes SET last_verified_at = ? WHERE id = ?", (stale_time, stale_id))
                
        # Search for "architecture" with min_trust = 0.6
        # Fresh_Node (effective trust 1.0) MUST be included
        # Stale_Node (effective trust ~0.001) MUST be filtered out!
        results = engine.search_nodes(TEST_DB, "architecture", min_trust=0.6, half_life_days=30.0)
        res_ids = [r["id"] for r in results]
        
        assert "Fresh_Node" in res_ids
        assert "Stale_Node" not in res_ids
    finally:
        cleanup_env()

if __name__ == "__main__":
    test_timedelta_import_fix()
    test_effective_trust_search_filtering()
    print("✅ All v2.1.1 bugfix & effective trust filtering tests passed!")
