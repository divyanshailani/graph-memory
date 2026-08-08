import os
import sys
import json
import importlib
import hashlib
from pathlib import Path
from graph_memory.core.engine import get_or_create_node as add_node, create_relation as add_relation, get_connection, write_transaction, resolve_canonical_id, now_iso

def pre_sweep_file_imports(db_path: str, file_node_id: str):
    """Deletes existing imports for a file before a fresh AST scan to prevent Ghost Edges."""
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                DELETE FROM Edges
                WHERE source_id = ? AND relation_type = 'IMPORTS'
            """, (file_node_id,))

def pre_sweep_file_components(db_path: str, file_node_id: str):
    """Soft-deletes all component nodes defined in a file before re-parsing to prune ghost nodes."""
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                UPDATE Nodes 
                SET is_deleted = 1, status = 'pruned', updated_at = ?
                WHERE id IN (
                    SELECT source_id FROM Edges WHERE target_id = ? AND relation_type = 'DEFINED_IN'
                )
            """, (now_iso(), file_node_id))

# Mapping extensions to the exact PyPI package required
PARSER_PACKAGES = {
    ".py": "tree-sitter-python",
    ".ts": "tree-sitter-typescript",
    ".tsx": "tree-sitter-typescript",
    ".js": "tree-sitter-javascript",
    ".jsx": "tree-sitter-javascript",
    ".go": "tree-sitter-go",
    ".rs": "tree-sitter-rust",
}

# The Query Map Builder as requested by the user
QUERY_MAP = {
    ".py": {
        "import_nodes": {"import_statement", "import_from_statement"},
        "function_nodes": {"function_definition"},
        "class_nodes": {"class_definition"},
        "call_nodes": {"call"},
    },
    ".ts": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
        "call_nodes": {"call_expression"},
    },
    ".tsx": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
        "call_nodes": {"call_expression"},
    },
    ".js": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
        "call_nodes": {"call_expression"},
    },
    ".jsx": {
        "import_nodes": {"import_statement"},
        "function_nodes": {"function_declaration", "method_definition", "arrow_function"},
        "class_nodes": {"class_declaration"},
        "call_nodes": {"call_expression"},
    },
    ".go": {
        "import_nodes": {"import_declaration", "import_spec"},
        "function_nodes": {"function_declaration", "method_declaration"},
        "class_nodes": {"type_declaration"},
        "call_nodes": {"call_expression"},
    },
    ".rs": {
        "import_nodes": {"use_declaration"},
        "function_nodes": {"function_item"},
        "class_nodes": {"struct_item", "enum_item", "trait_item"},
        "call_nodes": {"call_expression"},
    }
}

def load_parser(ext):
    """Dynamically loads tree-sitter language parser with multi-tier API fallbacks."""
    import tree_sitter
    package_name = PARSER_PACKAGES.get(ext)
    if not package_name:
        return None

    module_name = package_name.replace("-", "_")
    
    try:
        ts_module = importlib.import_module(module_name)
        lang_fn = None
        ext_clean = ext.strip('.')
        
        # Tier 1: Extension-specific functions (e.g. language_tsx, language_jsx)
        if ext == ".tsx":
            lang_fn = getattr(ts_module, "language_tsx", None)
        elif ext == ".jsx":
            lang_fn = getattr(ts_module, "language_jsx", None)
            
        # Tier 2: Check language_<ext_clean>, language_<package_suffix>, or generic language()
        if not lang_fn:
            pkg_suffix = module_name.split('_')[-1]
            lang_fn = (
                getattr(ts_module, f"language_{ext_clean}", None)
                or getattr(ts_module, f"language_{pkg_suffix}", None)
                or getattr(ts_module, "language", None)
            )
            
        if not lang_fn:
            raise AttributeError(f"Could not find language() or language_X() in {module_name}")
            
        lang = tree_sitter.Language(lang_fn())
        return tree_sitter.Parser(lang)
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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB safety cap for AST parsing

def extract_calls_and_inheritance(node, ext, entities, current_scope="", content_bytes=b"", depth=0):
    """Walks the AST node looking for function calls (CALLS) and class inheritance (EXTENDS) with depth cap."""
    if depth > 100:
        return
        
    qmap = QUERY_MAP.get(ext)
    if not qmap:
        return
        
    node_type = node.type
    
    if node_type in qmap["class_nodes"]:
        name_node = node.child_by_field_name("name")
        cls_name = name_node.text.decode('utf8') if name_node else None
        
        super_name = None
        super_node = node.child_by_field_name("superclasses") or node.child_by_field_name("heritage")
        if super_node:
            for child in super_node.children:
                if child.type in ("identifier", "type_identifier", "argument_list", "extends_clause"):
                    id_nodes = [c for c in child.children if c.type in ("identifier", "type_identifier")]
                    if id_nodes:
                        super_name = id_nodes[0].text.decode('utf8')
                        break
                    elif child.type in ("identifier", "type_identifier"):
                        super_name = child.text.decode('utf8')
                        break
                        
        if cls_name and super_name:
            entities["extends"].append({"sub_class": cls_name, "super_class": super_name})
            
    elif node_type in qmap.get("call_nodes", set()):
        func_node = node.child_by_field_name("function")
        call_name = None
        if func_node:
            if func_node.type == "identifier":
                call_name = func_node.text.decode('utf8')
            elif func_node.type in ("attribute", "member_expression"):
                attr_node = func_node.child_by_field_name("attribute") or func_node.child_by_field_name("property")
                if attr_node:
                    call_name = attr_node.text.decode('utf8')
                    
        if call_name and current_scope:
            entities["calls"].append({"caller": current_scope, "callee": call_name})

    new_scope = current_scope
    if node_type in qmap["function_nodes"]:
        name_node = node.child_by_field_name("name")
        if name_node:
            new_scope = name_node.text.decode('utf8')
    elif node_type in qmap["class_nodes"]:
        name_node = node.child_by_field_name("name")
        if name_node:
            new_scope = name_node.text.decode('utf8')

    for child in node.children:
        extract_calls_and_inheritance(child, ext, entities, new_scope, content_bytes, depth + 1)

def extract_entities(node, ext, entities, content_bytes, parent_path="", depth=0):
    """Recursively walks the AST and matches against QUERY_MAP extracting signatures, docstrings, line bounds, and snippets."""
    if depth > 100:
        return
        
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
        extract_entities(child, ext, entities, content_bytes, parent_path, depth + 1)

DEFAULT_IGNORE_DIRS = {
    "node_modules", "venv", ".venv", "env", ".env", "site-packages",
    "dist", "build", "target", "out", "__pycache__", ".git", ".hg", ".svn",
    ".tox", ".eggs", ".egg-info", ".pytest_cache", ".mypy_cache", ".cache",
    ".next", ".nuxt", "vendor"
}

def should_ignore_path(path: Path) -> bool:
    """Returns True if path is inside virtualenv, node_modules, build/dist, or cache directories."""
    parts = set(path.parts)
    if parts.intersection(DEFAULT_IGNORE_DIRS):
        return True
    for part in path.parts:
        lower_part = part.lower()
        if "site-packages" in lower_part or "venv" in lower_part or lower_part.endswith(".egg-info") or lower_part.endswith("-info"):
            return True
    return False

def ingest_file(db_path: str, file_path: str, agent_name: str = "Tree-sitter", rationale: str = "Single file incremental AST update") -> dict:
    """
    Incrementally re-parses a single changed file into the AST graph (<5ms).
    Updates component nodes, line ranges, signatures, docstrings, snippets, CALLS, and EXTENDS relations.
    Soft-deletes ghost component nodes before re-parsing.
    Enforces 10MB size cap and null-byte binary file checks.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        return {"status": "error", "message": f"File '{file_path}' not found."}
        
    if should_ignore_path(path):
        return {"status": "ignored", "message": f"File '{file_path}' is inside an ignored directory or third-party dependency package."}
        
    if path.stat().st_size > MAX_FILE_SIZE:
        return {"status": "ignored", "message": f"File '{path.name}' ({path.stat().st_size} bytes) exceeds maximum allowed size of 10MB."}
        
    ext = path.suffix
    if ext not in PARSER_PACKAGES:
        return {"status": "ignored", "message": f"Extension '{ext}' not supported for AST parsing."}
        
    parser = load_parser(ext)
    if not parser:
        return {"status": "error", "message": f"Parser for '{ext}' unavailable."}
        
    content = path.read_bytes()
    if b'\x00' in content[:1024]:
        return {"status": "ignored", "message": f"Binary file with null bytes detected for '{path.name}', skipping AST parse."}
    tree = parser.parse(content)
    
    entities = {"functions": [], "classes": [], "imports": [], "calls": [], "extends": []}
    extract_entities(tree.root_node, ext, entities, content)
    extract_calls_and_inheritance(tree.root_node, ext, entities, "", content)
    
    file_id = f"File_{path.name}"
    pre_sweep_file_components(db_path, file_id)
    
    file_hash = hashlib.sha256(content).hexdigest()
    mtime = path.stat().st_mtime
    
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
        
    for ext_data in entities["extends"]:
        sub_cls = f"Class_{ext_data['sub_class']}_{path.name}"
        super_cls = f"Class_{ext_data['super_class']}_{path.name}"
        add_node(db_path, super_cls, "Fact_Node", {"entity_type": "Component", "name": ext_data['super_class'], "component_type": "class", "source": "AST_Inheritance"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
        add_relation(db_path, sub_cls, super_cls, "EXTENDS", trust_score=1.0, verification_method="source_parse")
        
    for call_data in entities["calls"]:
        caller_id = f"Func_{call_data['caller']}_{path.name}"
        callee_id = f"Func_{call_data['callee']}_{path.name}"
        add_node(db_path, callee_id, "Fact_Node", {"entity_type": "Component", "name": call_data['callee'], "component_type": "function", "source": "AST_Call"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
        add_relation(db_path, caller_id, callee_id, "CALLS", trust_score=1.0, verification_method="source_parse")
        
    return {"status": "success", "file": str(path), "functions": len(entities["functions"]), "classes": len(entities["classes"]), "calls": len(entities["calls"]), "extends": len(entities["extends"])}

def ingest_codebase(db_path: str, directory: str, agent_name: str = "Tree-sitter", rationale: str = "Full project AST ingestion"):
    """Scans the directory, parses files, and builds the MOC graph with call graphs and inheritance."""
    directory = Path(directory).resolve()
    print(f"[*] Starting AST ingestion of {directory}")
    
    parsers = {}
    root_id = f"Project_{directory.name}"
    add_node(db_path, root_id, "Fact_Node", {"entity_type": "Project", "path": str(directory), "created_by": agent_name, "source": "AST", "confidence": 1.0}, trust_score=1.0, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
    
    created_mocs = set()
    
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
            
        if should_ignore_path(path):
            continue
            
        if path.stat().st_size > MAX_FILE_SIZE:
            print(f"[!] Skipping {path.name}: file exceeds 10MB limit.")
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
            if b'\x00' in content[:1024]:
                print(f"[!] Skipping {path.name}: binary file detected.")
                continue
            tree = parser.parse(content)
        except Exception as e:
            print(f"[!] Failed to parse {path.name}: {e}")
            continue
            
        entities = {"functions": [], "classes": [], "imports": [], "calls": [], "extends": []}
        extract_entities(tree.root_node, ext, entities, content)
        extract_calls_and_inheritance(tree.root_node, ext, entities, "", content)
        
        rel_parent = path.parent.relative_to(directory)
        moc_id = f"MOC_{rel_parent.name}" if rel_parent.name else f"MOC_{directory.name}"
        if moc_id not in created_mocs:
            add_node(db_path, moc_id, "Fact_Node", {"entity_type": "MOC_Hub", "dir": str(rel_parent), "created_by": agent_name, "source": "AST", "confidence": 1.0}, trust_score=1.0, verification_method="source_parse", link_to=root_id, link_type="PART_OF", agent_name=agent_name, rationale=rationale)
            created_mocs.add(moc_id)
            
        file_id = f"File_{path.name}"
        pre_sweep_file_components(db_path, file_id)
        
        file_hash = hashlib.sha256(content).hexdigest()
        mtime = path.stat().st_mtime
        
        add_node(
            db_path, 
            file_id, 
            "Fact_Node", 
            {
                "entity_type": "File", 
                "path": str(path.relative_to(directory)), 
                "file_hash": file_hash,
                "mtime": mtime,
                "created_by": agent_name, 
                "source": "AST", 
                "confidence": 1.0
            }, 
            trust_score=1.0, 
            verification_method="source_parse", 
            link_to=moc_id, 
            link_type="CONTAINS",
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
                    "file_path": str(path.relative_to(directory)),
                    "created_by": agent_name, 
                    "source": "AST", 
                    "confidence": 1.0
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
                    "file_path": str(path.relative_to(directory)),
                    "created_by": agent_name, 
                    "source": "AST", 
                    "confidence": 1.0
                }, 
                trust_score=1.0, 
                verification_method="source_parse", 
                link_to=file_id, 
                link_type="DEFINED_IN",
                agent_name=agent_name,
                rationale=rationale
            )
            
        for ext_data in entities["extends"]:
            sub_cls = f"Class_{ext_data['sub_class']}_{path.name}"
            super_cls = f"Class_{ext_data['super_class']}_{path.name}"
            add_node(db_path, sub_cls, "Fact_Node", {"entity_type": "Component", "name": ext_data['sub_class'], "component_type": "class", "source": "AST_Inheritance"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
            add_node(db_path, super_cls, "Fact_Node", {"entity_type": "Component", "name": ext_data['super_class'], "component_type": "class", "source": "AST_Inheritance"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
            add_relation(db_path, sub_cls, super_cls, "EXTENDS", trust_score=1.0, verification_method="source_parse")
            
        for call_data in entities["calls"]:
            caller_id = f"Func_{call_data['caller']}_{path.name}"
            callee_id = f"Func_{call_data['callee']}_{path.name}"
            add_node(db_path, caller_id, "Fact_Node", {"entity_type": "Component", "name": call_data['caller'], "component_type": "function", "source": "AST_Call"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
            add_node(db_path, callee_id, "Fact_Node", {"entity_type": "Component", "name": call_data['callee'], "component_type": "function", "source": "AST_Call"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
            add_relation(db_path, caller_id, callee_id, "CALLS", trust_score=1.0, verification_method="source_parse")
            
        pre_sweep_file_imports(db_path, file_id)
        for imp in set(entities["imports"]):
            clean_imp = imp.replace('"', '').replace("'", "").strip(';')
            target_id = f"Dependency_{clean_imp}"
            add_node(db_path, target_id, "Fact_Node", {"entity_type": "External_Dependency", "module": clean_imp, "created_by": agent_name, "source": "AST", "confidence": 1.0}, trust_score=0.8, verification_method="source_parse", link_to=root_id, link_type="USES", agent_name=agent_name, rationale=rationale)
            add_relation(db_path, file_id, target_id, "IMPORTS", trust_score=1.0, verification_method="source_parse")
            
    print("[*] AST Ingestion Complete!")
