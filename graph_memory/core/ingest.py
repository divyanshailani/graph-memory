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

def extract_docstring_from_node(node, content_bytes):
    """Extracts Python docstrings or comment blocks preceding/inside nodes."""
    body_node = node.child_by_field_name("body")
    if body_node:
        for child in body_node.children:
            if child.type == "expression_statement":
                str_child = child.children[0] if child.children else None
                if str_child and str_child.type in ("string", "concatenated_string"):
                    text = content_bytes[str_child.start_byte:str_child.end_byte].decode('utf-8', errors='ignore')
                    return text.strip('"' "' \n\t")
    return ""

def extract_entities(node, ext, entities, content_bytes, parent_path=""):
    """Recursively walks the AST and matches against QUERY_MAP extracting signatures, docstrings, line bounds, and snippets."""
    qmap = QUERY_MAP.get(ext)
    if not qmap:
        return
        
    node_type = node.type
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    node_text = content_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
    
    if node_type in qmap["function_nodes"]:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode('utf8') if name_node else "anonymous_func"
        sig_line = node_text.split('\n')[0].strip() if node_text else f"def {name}(...)"
        docstring = extract_docstring_from_node(node, content_bytes)
        
        lines = node_text.split('\n')
        snippet = '\n'.join(lines[:15]) + ('\n...' if len(lines) > 15 else '')
        
        entities["functions"].append({
            "name": name,
            "signature": sig_line,
            "docstring": docstring,
            "start_line": start_line,
            "end_line": end_line,
            "snippet": snippet
        })
        
    elif node_type in qmap["class_nodes"]:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode('utf8') if name_node else "AnonymousClass"
        sig_line = node_text.split('\n')[0].strip() if node_text else f"class {name}"
        docstring = extract_docstring_from_node(node, content_bytes)
        
        lines = node_text.split('\n')
        snippet = '\n'.join(lines[:15]) + ('\n...' if len(lines) > 15 else '')
        
        entities["classes"].append({
            "name": name,
            "signature": sig_line,
            "docstring": docstring,
            "start_line": start_line,
            "end_line": end_line,
            "snippet": snippet
        })
        
    elif node_type in qmap["import_nodes"]:
        text = node_text.replace('\n', ' ')
        if "from " in text:
            module = text.split("from ")[1].split(" import")[0]
            entities["imports"].append(module)
        elif "import " in text:
            module = text.split("import ")[1].split(" ")[0]
            entities["imports"].append(module)
        else:
            entities["imports"].append(text)

    for child in node.children:
        extract_entities(child, ext, entities, content_bytes, parent_path)

def ingest_file(db_path: str, file_path: str, agent_name: str = "Tree-sitter", rationale: str = "Single file incremental AST update") -> dict:
    """
    Incrementally re-parses a single changed file into the AST graph (<5ms).
    Updates component nodes, line ranges, signatures, docstrings, and snippets.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        return {"status": "error", "message": f"File '{file_path}' not found."}
        
    ext = path.suffix
    if ext not in PARSER_PACKAGES:
        return {"status": "ignored", "message": f"Extension '{ext}' not supported for AST parsing."}
        
    parser = load_parser(ext)
    if not parser:
        return {"status": "error", "message": f"Parser for '{ext}' unavailable."}
        
    content = path.read_bytes()
    tree = parser.parse(content)
    
    entities = {"functions": [], "classes": [], "imports": []}
    extract_entities(tree.root_node, ext, entities, content)
    
    import hashlib
    file_hash = hashlib.sha256(content).hexdigest()
    mtime = path.stat().st_mtime
    
    file_id = f"File_{path.name}"
    add_node(
        db_path, 
        file_id, 
        "Fact_Node", 
        {
            "entity_type": "File", 
            "path": str(path), 
            "file_hash": file_hash, 
            "mtime": mtime,
            "source": "AST"
        }, 
        trust_score=1.0, 
        verification_method="source_parse",
        agent_name=agent_name,
        rationale=rationale
    )
    
    for cls_data in entities["classes"]:
        cls_name = cls_data["name"]
        comp_id = f"Class_{cls_name}_{path.name}"
        add_node(
            db_path,
            comp_id,
            "Fact_Node",
            {
                "entity_type": "Component",
                "name": cls_name,
                "component_type": "class",
                "signature": cls_data["signature"],
                "docstring": cls_data["docstring"],
                "start_line": cls_data["start_line"],
                "end_line": cls_data["end_line"],
                "snippet": cls_data["snippet"],
                "file_path": str(path),
                "source": "AST"
            },
            trust_score=1.0,
            verification_method="source_parse",
            link_to=file_id,
            link_type="DEFINED_IN",
            agent_name=agent_name,
            rationale=rationale
        )
        
    for func_data in entities["functions"]:
        func_name = func_data["name"]
        comp_id = f"Func_{func_name}_{path.name}"
        add_node(
            db_path,
            comp_id,
            "Fact_Node",
            {
                "entity_type": "Component",
                "name": func_name,
                "component_type": "function",
                "signature": func_data["signature"],
                "docstring": func_data["docstring"],
                "start_line": func_data["start_line"],
                "end_line": func_data["end_line"],
                "snippet": func_data["snippet"],
                "file_path": str(path),
                "source": "AST"
            },
            trust_score=1.0,
            verification_method="source_parse",
            link_to=file_id,
            link_type="DEFINED_IN",
            agent_name=agent_name,
            rationale=rationale
        )
        
    return {"status": "success", "file": str(path), "functions": len(entities["functions"]), "classes": len(entities["classes"])}

def ingest_codebase(db_path, directory):
    """Scans the directory, parses files, and builds the MOC graph."""
    directory = Path(directory).resolve()
    print(f"[*] Starting AST ingestion of {directory}")
    
    parsers = {}
    root_id = f"Project_{directory.name}"
    add_node(db_path, root_id, "Fact_Node", {"entity_type": "Project", "path": str(directory), "created_by": "Tree-sitter", "source": "AST", "confidence": 1.0}, trust_score=1.0, verification_method="source_parse")
    
    created_mocs = set()
    
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
            
        if ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts or "venv" in path.parts or ".venv" in path.parts:
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
        extract_entities(tree.root_node, ext, entities, content)
        
        rel_parent = path.parent.relative_to(directory)
        moc_id = f"MOC_{rel_parent.name}" if rel_parent.name else f"MOC_{directory.name}"
        if moc_id not in created_mocs:
            add_node(db_path, moc_id, "Fact_Node", {"entity_type": "MOC_Hub", "dir": str(rel_parent), "created_by": "Tree-sitter", "source": "AST", "confidence": 1.0}, trust_score=1.0, verification_method="source_parse", link_to=root_id, link_type="PART_OF")
            created_mocs.add(moc_id)
            
        import hashlib
        file_hash = hashlib.sha256(content).hexdigest()
        mtime = path.stat().st_mtime
        
        file_id = f"File_{path.name}"
        add_node(
            db_path, 
            file_id, 
            "Fact_Node", 
            {
                "entity_type": "File", 
                "path": str(path.relative_to(directory)), 
                "file_hash": file_hash,
                "mtime": mtime,
                "created_by": "Tree-sitter", 
                "source": "AST", 
                "confidence": 1.0
            }, 
            trust_score=1.0, 
            verification_method="source_parse", 
            link_to=moc_id, 
            link_type="CONTAINS"
        )
        
        for cls_data in entities["classes"]:
            cls_name = cls_data["name"]
            comp_id = f"Class_{cls_name}_{path.name}"
            add_node(
                db_path, 
                comp_id, 
                "Fact_Node", 
                {
                    "entity_type": "Component", 
                    "name": cls_name, 
                    "component_type": "class", 
                    "signature": cls_data["signature"],
                    "docstring": cls_data["docstring"],
                    "start_line": cls_data["start_line"],
                    "end_line": cls_data["end_line"],
                    "snippet": cls_data["snippet"],
                    "file_path": str(path.relative_to(directory)),
                    "created_by": "Tree-sitter", 
                    "source": "AST", 
                    "confidence": 1.0
                }, 
                trust_score=1.0, 
                verification_method="source_parse", 
                link_to=file_id, 
                link_type="DEFINED_IN"
            )
            
        for func_data in entities["functions"]:
            func_name = func_data["name"]
            comp_id = f"Func_{func_name}_{path.name}"
            add_node(
                db_path, 
                comp_id, 
                "Fact_Node", 
                {
                    "entity_type": "Component", 
                    "name": func_name, 
                    "component_type": "function", 
                    "signature": func_data["signature"],
                    "docstring": func_data["docstring"],
                    "start_line": func_data["start_line"],
                    "end_line": func_data["end_line"],
                    "snippet": func_data["snippet"],
                    "file_path": str(path.relative_to(directory)),
                    "created_by": "Tree-sitter", 
                    "source": "AST", 
                    "confidence": 1.0
                }, 
                trust_score=1.0, 
                verification_method="source_parse", 
                link_to=file_id, 
                link_type="DEFINED_IN"
            )
            
        pre_sweep_file_imports(db_path, file_id)
        for imp in set(entities["imports"]):
            clean_imp = imp.replace('"', '').replace("'", "").strip(';')
            target_id = f"Dependency_{clean_imp}"
            add_node(db_path, target_id, "Fact_Node", {"entity_type": "External_Dependency", "module": clean_imp, "created_by": "Tree-sitter", "source": "AST", "confidence": 1.0}, trust_score=0.8, verification_method="source_parse", link_to=root_id, link_type="USES")
            add_relation(db_path, file_id, target_id, "IMPORTS", trust_score=1.0, verification_method="source_parse")
            
    print("[*] AST Ingestion Complete!")
