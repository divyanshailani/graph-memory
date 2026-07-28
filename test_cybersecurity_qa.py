import os
import sqlite3
import json
from graph_memory.core import engine
from graph_memory.core import ingest

TEST_DB = "test_security_qa.sqlite"
OVERSIZED_FILE = "huge_file.py"
BINARY_FILE = "fake_code.py"
MALFORMED_SYMBOL_FILE = "malformed_code.py"

def setup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", OVERSIZED_FILE, BINARY_FILE, MALFORMED_SYMBOL_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    engine.init_db(TEST_DB)
    
    # 1. Oversized file (>10MB)
    with open(OVERSIZED_FILE, "wb") as f:
        f.write(b"# " + b"a" * (11 * 1024 * 1024))
        
    # 2. Binary file with null bytes
    with open(BINARY_FILE, "wb") as f:
        f.write(b"def foo():\n\x00\x00\x00\xff\xfe\xfa")
        
    # 3. Code with newlines/control chars in symbol
    with open(MALFORMED_SYMBOL_FILE, "w", encoding="utf-8") as f:
        f.write("def func_with_normal_name():\n    pass\n")

def cleanup_env():
    for f in [TEST_DB, f"{TEST_DB}-wal", f"{TEST_DB}-shm", OVERSIZED_FILE, BINARY_FILE, MALFORMED_SYMBOL_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

def test_oversized_file_protection():
    setup_env()
    try:
        res = ingest.ingest_file(TEST_DB, OVERSIZED_FILE)
        assert res.get("status") in ("ignored", "error")
        assert "exceeds maximum allowed size" in res.get("message", "").lower() or "too large" in res.get("message", "").lower()
    finally:
        cleanup_env()

def test_binary_file_null_byte_protection():
    setup_env()
    try:
        res = ingest.ingest_file(TEST_DB, BINARY_FILE)
        assert res.get("status") in ("ignored", "error")
        assert "binary" in res.get("message", "").lower() or "null byte" in res.get("message", "").lower()
    finally:
        cleanup_env()

def test_recursion_depth_protection():
    setup_env()
    try:
        # Create 150-nested paren expression
        nested_code = "x = " + "(" * 150 + "1" + ")" * 150
        nested_file = "nested_expr.py"
        with open(nested_file, "w") as f:
            f.write(nested_code)
            
        res = ingest.ingest_file(TEST_DB, nested_file)
        assert res.get("status") == "success"
        if os.path.exists(nested_file):
            os.remove(nested_file)
    finally:
        cleanup_env()

if __name__ == "__main__":
    test_oversized_file_protection()
    test_binary_file_null_byte_protection()
    test_recursion_depth_protection()
    print("✅ All cybersecurity QA security tests passed!")
