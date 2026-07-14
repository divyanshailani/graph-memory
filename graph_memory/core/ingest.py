import os
import sys
import json
import importlib
from pathlib import Path
from graph_memory.core.engine import get_or_create_node as add_node, create_relation as add_relation, get_connection, write_transaction

def pre_sweep_file_imports(db_path: str, file_node_id: str):
    """Deletes existing imports for a file before a fresh AST scan to prevent Ghost Edges."""
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                DELETE FROM Edges
                WHERE source_id = ? AND relation_type = 'IMPORTS'
            """, (file_node_id,))

# Mapping extensions to the exact PyPI package required
PARSER_PACKAGES = {
    ".py": "tree-sitter-python",
    ".ts": "tree-sitter-typescript",
    ".js": "tree-sitter-javascript",
    ".go": "tree-sitter-go",
    ".rs": "tree-sitter-rust",
}

# The Query Map Builder as requested by the user
QUERY_MAP = {
    ".py": {
        "import_nodes": {"import_statement", "import_from_statement"},
        "function_nodes": {"function_definition"},
        "class_nodes": {"class_definition"},
    },
    ".ts": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
    },
    ".js": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
    },
    ".go": {
        "import_nodes": {"import_declaration", "import_spec"},
        "function_nodes": {"function_declaration", "method_declaration"},
        "class_nodes": {"type_declaration"},
    },
    ".rs": {
        "import_nodes": {"use_declaration"},
        "function_nodes": {"function_item"},
        "class_nodes": {"struct_item", "enum_item", "trait_item"},
    }
}

def load_parser(ext):
    """Dynamically loads the tree-sitter parser, warning if missing."""
    import tree_sitter
    package_name = PARSER_PACKAGES.get(ext)
    if not package_name:
        return None

    # Replace hyphens with underscores for module import
    module_name = package_name.replace("-", "_")
    
    try:
        ts_module = importlib.import_module(module_name)
        
        # Handle v0.23+ breaking change for typescript and others
        if hasattr(ts_module, "language"):
            lang = tree_sitter.Language(ts_module.language())
        elif hasattr(ts_module, "language_typescript") and module_name == "tree_sitter_typescript":
            lang = tree_sitter.Language(ts_module.language_typescript())
        else:
            # Fallback if there are other language_* functions (e.g. language_javascript)
            lang_func = getattr(ts_module, f"language_{module_name.split('_')[-1]}", None)
            if lang_func:
                lang = tree_sitter.Language(lang_func())
            else:
                raise AttributeError(f"Could not find language() or language_X() in {module_name}")
                
        parser = tree_sitter.Parser(lang)
        return parser
    except ImportError:
        print(f"[!] {ext} file detected, but parser missing. Run: pip install epistemic-graph-memory[{ext.strip('.')}]")
        return None

def extract_entities(node, ext, entities, parent_path=""):
    """Recursively walks the AST and matches against the QUERY_MAP."""
    qmap = QUERY_MAP.get(ext)
    if not qmap:
        return
        
    node_type = node.type
    
    # Try to extract the name if it's a function or class
    if node_type in qmap["function_nodes"]:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode('utf8') if name_node else "anonymous_func"
        entities["functions"].append(name)
    elif node_type in qmap["class_nodes"]:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode('utf8') if name_node else "AnonymousClass"
        entities["classes"].append(name)
    elif node_type in qmap["import_nodes"]:
        # We grab the full text of the import for simplicity in building edges
        text = node.text.decode('utf8').replace('\n', ' ')
        # Very simple heuristic to extract the module name for Python
        if "from " in text:
            module = text.split("from ")[1].split(" import")[0]
            entities["imports"].append(module)
        elif "import " in text:
            module = text.split("import ")[1].split(" ")[0]
            entities["imports"].append(module)
        else:
            # Fallback for other languages
            entities["imports"].append(text)

    for child in node.children:
        extract_entities(child, ext, entities)

def ingest_codebase(db_path, directory):
    """Scans the directory, parses files, and builds the MOC graph."""
    directory = Path(directory).resolve()
    print(f"[*] Starting AST ingestion of {directory}")
    
    # Map of loaded parsers
    parsers = {}
    
    # We create the root Project Node first
    root_id = f"Project_{directory.name}"
    add_node(db_path, root_id, "Project", {"path": str(directory)}, trust_score=1.0)
    
    # Track created MOCs to avoid duplicates
    created_mocs = set()
    
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
            
        # Ignore common bad directories
        if ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts or "venv" in path.parts:
            continue
            
        ext = path.suffix
        if ext not in PARSER_PACKAGES:
            continue
            
        if ext not in parsers:
            parsers[ext] = load_parser(ext)
            
        parser = parsers[ext]
        if parser is None:
            continue
            
        try:
            content = path.read_bytes()
            tree = parser.parse(content)
        except Exception as e:
            print(f"[!] Failed to parse {path.name}: {e}")
            continue
            
        entities = {"functions": [], "classes": [], "imports": []}
        extract_entities(tree.root_node, ext, entities)
        
        # 1. Create the MOC Hub if it doesn't exist
        # We group by the parent directory name
        rel_parent = path.parent.relative_to(directory)
        moc_id = f"MOC_{rel_parent.name}" if rel_parent.name else f"MOC_{directory.name}"
        if moc_id not in created_mocs:
            add_node(db_path, moc_id, "MOC_Hub", {"dir": str(rel_parent)}, trust_score=1.0, link_to=root_id, link_type="PART_OF")
            created_mocs.add(moc_id)
            
        # 2. Create the File Node
        file_id = f"File_{path.name}"
        add_node(db_path, file_id, "File", {"path": str(path.relative_to(directory))}, trust_score=1.0, link_to=moc_id, link_type="CONTAINS")
        
        # 3. Create the Component Nodes (Classes and Functions)
        for cls in set(entities["classes"]):
            comp_id = f"Class_{cls}_{path.name}"
            add_node(db_path, comp_id, "Component", {"name": cls, "type": "class"}, trust_score=1.0, link_to=file_id, link_type="DEFINED_IN")
            
        for func in set(entities["functions"]):
            comp_id = f"Func_{func}_{path.name}"
            add_node(db_path, comp_id, "Component", {"name": func, "type": "function"}, trust_score=1.0, link_to=file_id, link_type="DEFINED_IN")
            
        # 4. Create the Directional Edges (The Dependency Arrow)
        pre_sweep_file_imports(db_path, file_id)
        for imp in set(entities["imports"]):
            clean_imp = imp.replace('"', '').replace("'", "").strip(';')
            target_id = f"Dependency_{clean_imp}"
            # Ensure the target node exists as an abstract dependency
            add_node(db_path, target_id, "External_Dependency", {"module": clean_imp}, trust_score=0.8, link_to=root_id, link_type="USES")
            # Create the arrow FROM the importing file TO the imported file/module
            add_relation(db_path, file_id, target_id, "IMPORTS", trust_score=1.0)
            
    print("[*] AST Ingestion Complete!")
