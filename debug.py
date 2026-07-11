from graph_memory.core.engine import get_or_create_node, create_relation, get_db_path, get_connection
db_path = ".agents/graph_memory.sqlite"

original_add_node = get_or_create_node
original_add_relation = create_relation

def mock_add_node(*args, **kwargs):
    print("add_node:", args[1])
    try:
        return original_add_node(*args, **kwargs)
    except Exception as e:
        print("FAIL add_node", e)
        raise e

def mock_add_relation(*args, **kwargs):
    print("add_relation:", args[1], "->", args[2])
    try:
        return original_add_relation(*args, **kwargs)
    except Exception as e:
        print("FAIL add_relation", e)
        raise e

import graph_memory.core.ingest
graph_memory.core.ingest.add_node = mock_add_node
graph_memory.core.ingest.add_relation = mock_add_relation

try:
    graph_memory.core.ingest.ingest_codebase(db_path, ".")
except Exception as e:
    pass
