import json
from pathlib import Path
from graph_memory.core import engine
from graph_memory.core.knowledge import extract_knowledge_cards, generate_repo_wiki
from graph_memory.core.memory import reflect_session_memory

def test_knowledge_cards_extraction(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)
    
    # Add dummy nodes for classification
    engine.get_or_create_node(db_path, "Func_test_ui", "Fact_Node", {"entity_type": "Component", "path": "src/ui/Button.tsx", "docstring": "UI Button component"})
    engine.get_or_create_node(db_path, "Func_test_build", "Fact_Node", {"entity_type": "Component", "path": "docker/Dockerfile", "docstring": "Docker build file"})
    engine.get_or_create_node(db_path, "Dep_neo4j", "Fact_Node", {"entity_type": "External_Dependency", "module": "neo4j", "docstring": "Neo4j graph database"})

    res = extract_knowledge_cards(db_path, str(tmp_path / ".agents/wiki"))
    assert res["status"] == "success"
    assert res["cards_count"] > 0
    assert Path(res["index_file"]).exists()

def test_repo_wiki_generation(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)
    
    engine.get_or_create_node(db_path, "MOC_Core", "Fact_Node", {"entity_type": "MOC_Hub", "dir": "graph_memory/core"})
    engine.get_or_create_node(db_path, "File_engine.py", "Fact_Node", {"entity_type": "File", "path": "graph_memory/core/engine.py", "file_hash": "abcdef123456"})

    res = generate_repo_wiki(db_path, str(tmp_path / ".agents/wiki"), repo_name="TestRepo")
    assert res["status"] == "success"
    assert res["wiki_files_count"] > 0
    assert Path(res["index_file"]).exists()

def test_session_memory_reflection(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    engine.init_db(db_path)
    
    engine.get_or_create_node(db_path, "NodeA", "Fact_Node", {"entity_type": "Component"})
    engine.record_decision_ledger(db_path, "NodeA", "AgentA", "Refactored AST ingester ignore logic", "Avoid venv third-party code pollution")

    res = reflect_session_memory(db_path, str(tmp_path / ".agents"))
    assert res["status"] == "success"
    assert res["memories_count"] == 5
