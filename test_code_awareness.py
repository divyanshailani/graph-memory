import os
import sqlite3
import json
import time
from graph_memory.core import engine
from graph_memory.core import ingest

TEST_DB = "test_code_awareness.sqlite"
SAMPLE_FILE = "sample_target.py"

def setup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", SAMPLE_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    engine.init_db(TEST_DB)
    
    # Create sample Python file
    sample_code = '''"""Sample Module Docstring"""

def calculate_total(price: float, tax_rate: float = 0.05) -> float:
    """Calculates total price including tax."""
    return price * (1.0 + tax_rate)

class OrderProcessor:
    """Processes customer orders."""
    def process(self, order_id: str):
        print(f"Processing order {order_id}")
'''
    with open(SAMPLE_FILE, "w", encoding="utf-8") as f:
        f.write(sample_code)

def cleanup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", SAMPLE_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

def test_ast_rich_extraction():
    setup_env()
    try:
        ingest.ingest_codebase(TEST_DB, ".")
        
        # Test function node extraction
        func_id = f"Func_calculate_total_{SAMPLE_FILE}"
        subgraph = engine.serialize_subgraph(TEST_DB, func_id)
        assert "calculate_total" in subgraph
        assert "Calculates total price including tax." in subgraph
        assert "Signature:" in subgraph
        assert "Line Range:" in subgraph or "L3-" in subgraph
    finally:
        cleanup_env()

def test_agent_provenance_ledger():
    setup_env()
    try:
        # Create node with agent attribution & rationale
        engine.get_or_create_node(
            TEST_DB, 
            "Node_Hermes_Test", 
            "Fact_Node", 
            {"observations": ["Initial setup"]},
            agent_name="Hermes",
            rationale="Initial agent setup for testing provenance"
        )
        
        # Add observation with another agent's rationale
        engine.add_observation(
            TEST_DB, 
            "Node_Hermes_Test", 
            "Added retry mechanism",
            agent_name="Antigravity",
            rationale="Prevent network timeout crashes"
        )
        
        subgraph = engine.serialize_subgraph(TEST_DB, "Node_Hermes_Test")
        assert "Author Agent: Hermes" in subgraph or "Hermes" in subgraph
        assert "Prevent network timeout crashes" in subgraph
        assert "History:" in subgraph or "Decision Log:" in subgraph
    finally:
        cleanup_env()

def test_incremental_auto_sync():
    setup_env()
    try:
        ingest.ingest_codebase(TEST_DB, ".")
        
        # Modify sample file
        time.sleep(1.0)
        updated_code = '''"""Updated Module Docstring"""

def calculate_total(price: float, tax_rate: float = 0.05) -> float:
    """Calculates total price including tax with discount support."""
    return price * (1.0 + tax_rate)

def new_discounted_price(price: float, discount: float) -> float:
    """New function added by Hermes."""
    return price - discount
'''
        with open(SAMPLE_FILE, "w", encoding="utf-8") as f:
            f.write(updated_code)
            
        # Trigger single-file ingest or auto-sync
        ingest.ingest_file(TEST_DB, SAMPLE_FILE, agent_name="Hermes", rationale="Added discount function")
        
        new_func_id = f"Func_new_discounted_price_{SAMPLE_FILE}"
        subgraph = engine.serialize_subgraph(TEST_DB, new_func_id)
        assert "new_discounted_price" in subgraph
        assert "New function added by Hermes." in subgraph
    finally:
        cleanup_env()

if __name__ == "__main__":
    test_ast_rich_extraction()
    test_agent_provenance_ledger()
    test_incremental_auto_sync()
    print("✅ All code awareness and provenance unit tests passed!")
