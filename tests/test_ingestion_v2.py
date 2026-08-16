import os
import sqlite3
import json
import time
from pathlib import Path
from graph_memory.core import engine
from graph_memory.core import ingest

TEST_DB = "test_ingestion_v2.sqlite"
SAMPLE_PYTHON = "sample_v2_code.py"
SAMPLE_TSX = "SampleComponent.tsx"
NS = ingest.project_namespace(Path(".").resolve())

def setup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", SAMPLE_PYTHON, SAMPLE_TSX]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    engine.init_db(TEST_DB)
    
    # Python sample code with calls and inheritance
    py_code = '''class BaseEngine:
    def execute(self):
        print("Base execute")

class SmartEngine(BaseEngine):
    def run_task(self):
        self.execute()
        helper_function()

def helper_function():
    print("Helper executed")
'''
    with open(SAMPLE_PYTHON, "w", encoding="utf-8") as f:
        f.write(py_code)
        
    # TSX sample code
    tsx_code = '''import React from 'react';

interface Props {
    title: string;
}

export const HeaderComponent: React.FC<Props> = ({ title }) => {
    return <h1>{title}</h1>;
};
'''
    with open(SAMPLE_TSX, "w", encoding="utf-8") as f:
        f.write(tsx_code)

def cleanup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", SAMPLE_PYTHON, SAMPLE_TSX]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

def test_calls_and_extends_extraction():
    setup_env()
    try:
        ingest.ingest_codebase(TEST_DB, ".")
        
        # Check Class_SmartEngine -[EXTENDS]-> Class_BaseEngine (same file)
        subgraph_sub = engine.serialize_subgraph(TEST_DB, f"Class_SmartEngine_{NS}/{SAMPLE_PYTHON}")
        assert "EXTENDS" in subgraph_sub or "BaseEngine" in subgraph_sub
        
        # Check Func_run_task -[CALLS]-> Func_helper_function (same file)
        subgraph_run = engine.serialize_subgraph(TEST_DB, f"Func_run_task_{NS}/{SAMPLE_PYTHON}")
        assert "CALLS" in subgraph_run or "helper_function" in subgraph_run
    finally:
        cleanup_env()

def test_ghost_component_pruning():
    setup_env()
    try:
        ingest.ingest_codebase(TEST_DB, ".")
        
        # Verify helper_function exists
        func_id = f"Func_helper_function_{NS}/{SAMPLE_PYTHON}"
        subgraph_before = engine.serialize_subgraph(TEST_DB, func_id)
        assert "helper_function" in subgraph_before
        
        # Modify file to remove helper_function
        updated_py_code = '''class BaseEngine:
    def execute(self):
        print("Base execute")

class SmartEngine(BaseEngine):
    def run_task(self):
        self.execute()
'''
        with open(SAMPLE_PYTHON, "w", encoding="utf-8") as f:
            f.write(updated_py_code)
            
        # Re-ingest single file
        ingest.ingest_file(TEST_DB, SAMPLE_PYTHON, agent_name="Hermes", rationale="Pruned helper_function")
        
        # Verify helper_function is now soft-deleted (pruned)
        with engine.get_connection(TEST_DB) as conn:
            row = conn.execute("SELECT is_deleted, status FROM Nodes WHERE id = ?", (func_id,)).fetchone()
            assert row is not None
            assert row[0] == 1  # is_deleted == 1
    finally:
        cleanup_env()

def test_tsx_file_ingestion():
    setup_env()
    try:
        ingest.ingest_codebase(TEST_DB, ".")
        
        # Check File node for SampleComponent.tsx exists
        file_id = f"File_{NS}/{SAMPLE_TSX}"
        subgraph = engine.serialize_subgraph(TEST_DB, file_id)
        assert "SampleComponent.tsx" in subgraph
    finally:
        cleanup_env()

if __name__ == "__main__":
    test_calls_and_extends_extraction()
    test_ghost_component_pruning()
    test_tsx_file_ingestion()
    print("✅ All v2.0.0 ingestion unit tests passed!")
