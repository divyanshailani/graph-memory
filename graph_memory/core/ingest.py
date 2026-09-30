import os
import re
import sys
import json
import importlib
import hashlib
import posixpath
from pathlib import Path
from graph_memory.core.engine import get_or_create_node, create_relation as add_relation, get_connection, write_transaction, resolve_canonical_id, now_iso, init_db, bulk_upsert_nodes

def add_node(db_path, *args, **kwargs):
    """
    AST ingestion wrapper around engine.get_or_create_node.
    Mechanical re-verifications are not agent decisions, so they are kept out of the
    Decision_Ledger (log_ledger=False); provenance still lands in node properties/history.
    """
    kwargs.setdefault("log_ledger", False)
    return get_or_create_node(db_path, *args, **kwargs)

def pre_sweep_file_imports(db_path: str, file_node_id: str):
    """Deletes existing imports for a file before a fresh AST scan to prevent Ghost Edges."""
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                DELETE FROM Edges
                WHERE source_id = ? AND relation_type = 'IMPORTS'
            """, (file_node_id,))

def pre_sweep_file_edges(db_path: str, file_node_id: str):
    """
    Deletes existing CALLS and EXTENDS edges for all components defined in a file
    before re-parsing to prevent ghost edges when code structure changes.
    
    This is called by ingest_file to ensure that removed function calls or changed
    inheritance relationships don't leave stale edges in the graph.
    """
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            # Get all component IDs defined in this file
            component_ids = [
                row[0] for row in conn.execute(
                    "SELECT source_id FROM Edges WHERE target_id = ? AND relation_type = 'DEFINED_IN'",
                    (file_node_id,)
                ).fetchall()
            ]
            
            if not component_ids:
                return
            
            # Delete CALLS and EXTENDS edges where these components are the source
            placeholders = ",".join("?" * len(component_ids))
            conn.execute(
                f"DELETE FROM Edges WHERE source_id IN ({placeholders}) AND relation_type IN ('CALLS', 'EXTENDS')",
                component_ids
            )

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
    try:
        import tree_sitter
    except ImportError:
        raise ImportError(
            "tree-sitter is required for AST ingestion but is not installed. "
            "Install it with:  pip install 'epistemic-graph-memory[ast]'"
        )
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
        receiver = None
        if func_node:
            if func_node.type == "identifier":
                call_name = func_node.text.decode('utf8')
            elif func_node.type in ("attribute", "member_expression", "field_expression"):
                attr_node = (func_node.child_by_field_name("attribute")
                             or func_node.child_by_field_name("property")
                             or func_node.child_by_field_name("field"))
                recv_node = (func_node.child_by_field_name("object")
                             or func_node.child_by_field_name("receiver"))
                if attr_node:
                    call_name = attr_node.text.decode('utf8')
                if recv_node is not None:
                    # Receiver text drives cross-file import resolution; cap it
                    # so huge member expressions never bloat the edge payload.
                    receiver = recv_node.text.decode('utf8', 'ignore')[:64]

        if call_name and current_scope:
            entities["calls"].append({"caller": current_scope, "callee": call_name, "receiver": receiver})

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

# ---------------------------------------------------------------------------
# Project-Scoped Node Identity (v3.4.0)
#
# Node IDs are namespaced by project root ("<name>_<6-char path hash>") and
# keyed by repo-relative POSIX paths. This prevents two classes of collision
# when a single database serves multiple checkouts: identical basenames in
# different directories (two utils.py files) and identical relative paths in
# different projects (two repos both containing src/utils.py).
# ---------------------------------------------------------------------------

PROJECT_ROOT_MARKERS = (".git", "pyproject.toml", "setup.py", "package.json", "go.mod", "Cargo.toml")

def _find_project_root(start: Path) -> Path:
    """Nearest ancestor of `start` containing a project marker file. Falls back to the starting directory."""
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if any((candidate / marker).exists() for marker in PROJECT_ROOT_MARKERS):
            return candidate
    return current

PROJECT_ID_FILE = os.path.join(".agents", "project_id")

def project_namespace(root: Path) -> str:
    """Stable per-project namespace: sanitized root name + 6-char identity token.

    v3.9.0: the whole namespace string prefers a committed `.agents/project_id`
    file. A repo that is moved, cloned, or checked out at a second path — even
    under a different directory name — keeps the namespace its nodes were keyed
    with, so the store survives relocation instead of forcing a full re-ingest.
    First use creates the file (gitignored by the default template — commit it
    to make the identity portable). Without it the token falls back to the
    6-char sha1 of the resolved absolute path, matching every namespace minted
    before v3.9.0.
    """
    root = Path(root).resolve()
    id_file = root / PROJECT_ID_FILE
    try:
        stored = id_file.read_text(encoding="utf-8").strip()
    except OSError:
        stored = ""
    if stored:
        return stored
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:6]
    clean_name = re.sub(r"[^A-Za-z0-9]", "_", root.name).strip("_") or "project"
    namespace = f"{clean_name}_{digest}"
    try:
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(namespace + "\n", encoding="utf-8")
    except OSError:
        pass  # read-only checkout: path-hash namespace still works, just not portable
    return namespace

def sanitize_import_module(module: str, ext: str):
    """
    Cleans a raw import string into a dependency module name, or returns None for
    targets that must not become External_Dependency nodes: relative Python imports
    (`from . import x`, `from ...pkg import y`) and relative JS/TS paths (`./x`, `../y`).
    """
    if not module:
        return None
    clean = module.strip().strip("'\"").strip()
    if ext == ".py":
        clean = clean.lstrip(".")
    if not clean or clean.startswith((".", "/", "\\")):
        return None
    clean = clean.strip(";").strip()
    return clean or None

JS_IMPORT_RE = re.compile(
    r"""import\s+(?:[\w$]+\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|export\s+(?:\*|\{[^}]*\})\s+from\s+['"]([^'"]+)['"]"""
    r"""|\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)"""
)

def _walk_import_nodes(node, types, out, level=0):
    if level > 100:
        return
    if node.type in types:
        out.append(node)
    for child in node.children:
        _walk_import_nodes(child, types, out, level + 1)


def _text(node, content):
    return node.text.decode("utf-8", "ignore") if node is not None else ""


def _py_bindings(root, content):
    """Python: {local_name: {"module": dotted origin, "level": relative depth, "orig": imported name}}.

    `import a.b as c`        -> c -> module a.b   (orig a.b)
    `import a.b`             -> a -> module a     (only the first segment binds)
    `from .x import y`       -> y -> module x, level 1   (`from . import y` -> module "", level 1)
    `from a.b import c as d` -> d -> module a.b.c, level 0
    `from a.b import c`      -> c -> module a.b, level 0
    `from m import x.y`      -> x -> module m, orig x.y  (only x binds)
    """
    bindings = {}
    nodes = []
    _walk_import_nodes(root, {"import_statement", "import_from_statement"}, nodes)
    for node in nodes:
        children = node.children
        # Anonymous keyword nodes appear in children; the module precedes
        # `import`, the bound names follow it.
        kw = next((i for i, c in enumerate(children) if c.type == "import"), len(children))

        if node.type == "import_statement":
            for child in children:
                if child.type == "dotted_name":
                    seg = _text(child, content).split(".")[0]
                    bindings[seg] = {"module": seg, "level": 0, "orig": seg}
                elif child.type == "aliased_import":
                    name_n = child.child_by_field_name("name")
                    alias_n = child.child_by_field_name("alias")
                    if name_n is None:
                        continue
                    orig = _text(name_n, content)
                    local = _text(alias_n, content) if alias_n is not None else orig.split(".")[0]
                    bindings[local] = {"module": orig, "level": 0, "orig": orig}
            continue

        module = ""
        level = 0
        for child in children[:kw]:
            if child.type == "dotted_name":
                module = _text(child, content)
            elif child.type == "relative_import":
                for g in child.children:
                    # Newer grammars nest the dots in an import_prefix node.
                    for t in (g.children if g.type == "import_prefix" else (g,)):
                        if t.type == ".":
                            level += 1
                        elif t.type == "ellipsis":
                            level += 3
                        elif t.type in ("dotted_name", "identifier"):
                            module = _text(t, content)

        for child in children[kw + 1:]:
            names = []
            if child.type == "dotted_name":
                names = [(_text(child, content), None)]
            elif child.type == "aliased_import":
                nm = child.child_by_field_name("name")
                al = child.child_by_field_name("alias")
                if nm is not None:
                    names.append((_text(nm, content), _text(al, content) if al is not None else None))
            elif child.type == "parenthesized_expression":
                for item in child.children:
                    if item.type == "dotted_name":
                        names += [(s, None) for s in _text(item, content).split(".")]
                    elif item.type == "identifier":
                        names.append((_text(item, content), None))
                    elif item.type == "aliased_import":
                        nm = item.child_by_field_name("name")
                        al = item.child_by_field_name("alias")
                        if nm is not None:
                            names.append((_text(nm, content), _text(al, content) if al is not None else None))
            # wildcard_import and keywords bind nothing.
            for orig, alias in names:
                local = alias or orig.split(".")[0]
                if not local or local == "*":
                    continue
                if alias:
                    full = f"{module}.{orig}" if module else orig
                    bindings[local] = {"module": full, "level": level, "orig": orig.split(".")[0]}
                else:
                    bindings[local] = {"module": module, "level": level, "orig": orig}
    return bindings


def _ts_bindings(content, bindings):
    """JS/TS: regex over raw text — module specifier plus per-name aliases.
    `import x from 'm'`, `import {a as b} from 'm'`, `import * as ns from 'm'`,
    `const x = require('m')`, `export ... from 'm'`."""
    for m in JS_IMPORT_RE.finditer(content):
        src = m.group(1) or m.group(2) or m.group(3)
        stmt = content[max(0, m.start() - 400):m.end()]
        brace = re.search(r"\{([^}]*)\}", stmt)
        seen_names = False
        if brace:
            for part in brace.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                am = re.match(r"(?:default\s+)?[\w$]+(?:\s+as\s+([\w$]+))?$", part)
                if am:
                    local = am.group(1) or part.split()[0]
                    bindings[local] = {"module": src, "level": 0, "orig": part.split()[0]}
                    seen_names = True
        ns = re.search(r"import\s+\*\s+as\s+([\w$]+)", stmt)
        if ns:
            bindings[ns.group(1)] = {"module": src, "level": 0, "orig": "*"}
            seen_names = True
        top = re.match(r"\s*import\s+([\w$]+)\s+from", stmt)
        if top:
            bindings[top.group(1)] = {"module": src, "level": 0, "orig": "default"}
            seen_names = True
        rq = re.search(r"(?:const|let|var)\s+([\w$]+)\s*=\s*require", stmt)
        if rq:
            bindings[rq.group(1)] = {"module": src, "level": 0, "orig": "*"}
            seen_names = True
        if not seen_names and src:
            bindings.setdefault(f"__module__:{src}", {"module": src, "level": 0, "orig": "*"})


def _go_bindings(root, content):
    """Go: import_spec / import_spec_list; default local = final package-path segment."""
    bindings = {}
    nodes = []
    _walk_import_nodes(root, {"import_spec"}, nodes)
    for node in nodes:
        path_n = node.child_by_field_name("path")
        if path_n is None:
            continue
        src = _text(path_n, content).strip('"')
        name_n = node.child_by_field_name("name")
        local = _text(name_n, content).strip("_") if name_n is not None and _text(name_n, content) not in (".", "_") else ""
        if not local:
            local = src.rsplit("/", 1)[-1]
        if local:
            bindings[local] = {"module": src, "level": 0, "orig": local}
    return bindings


def _rs_bindings(content, bindings):
    """Rust: `use a::b::{c, d as e};` — regex; local = last segment / alias; `self::x` is relative."""
    for m in re.finditer(r"use\s+(?:pub\s+)?([^;]+);", content):
        body = m.group(1)
        outer = body.split("::", 1)[0] if "{" not in body else body.split("::{", 1)[0]
        level = 1 if outer in ("crate", "super", "self") else 0
        base = body
        names = [body.rsplit("::", 1)[-1]]
        group = re.search(r"\{([^}]*)\}", body)
        if group:
            names = [p.strip() for p in group.group(1).split(",") if p.strip()]
            base = body[:group.start()].rstrip(":")
            level = 1 if base.split("::", 1)[0] in ("crate", "super", "self") else level
        for entry in names:
            am = re.match(r"([\w]+)(?:\s+as\s+(\w+))?$", entry)
            if not am:
                continue
            orig = am.group(1)
            local = am.group(2) or (orig if orig != "self" else base.rsplit("::", 1)[-1])
            bindings[local] = {"module": base, "level": level, "orig": orig}


def _collect_import_bindings(root, ext, content):
    """Per-file import bindings used by cross-file call resolution (v3.9.0).
    Stored on File nodes as properties.bindings; keys are bound local names
    (plus `__module__:<src>` markers for nameless JS side-effect imports)."""
    text = content.decode("utf-8", "ignore")
    bindings = {}
    try:
        if ext == ".py":
            bindings.update(_py_bindings(root, text))
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            _ts_bindings(text, bindings)
        elif ext == ".go":
            bindings.update(_go_bindings(root, text))
        elif ext == ".rs":
            bindings.update(_rs_bindings(text, bindings))
    except Exception:
        return {}  # binding extraction must never break ingestion
    # Cap payload size: a file with pathological binding counts is truncated.
    if len(bindings) > 400:
        bindings = dict(list(bindings.items())[:400])
    return bindings

def ingest_file(db_path: str, file_path: str, agent_name: str = "Tree-sitter", rationale: str = "Single file incremental AST update", root: str = None) -> dict:
    """
    Incrementally re-parses a single changed file into the AST graph (<5ms).
    Updates component nodes, line ranges, signatures, docstrings, snippets, CALLS, and EXTENDS relations.
    Soft-deletes ghost component nodes before re-parsing.
    Enforces 10MB size cap and null-byte binary file checks.
    Pass `root` to pin the project namespace explicitly (monorepo-safe); by default
    the enclosing project root is detected via marker files.
    """
    init_db(db_path)
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
        
    try:
        parser = load_parser(ext)
    except ImportError as e:
        return {"status": "error", "message": str(e)}
    if not parser:
        return {"status": "error", "message": f"Parser for '{ext}' unavailable."}
        
    content = path.read_bytes()
    if b'\x00' in content[:1024]:
        return {"status": "ignored", "message": f"Binary file with null bytes detected for '{path.name}', skipping AST parse."}
    tree = parser.parse(content)
    
    entities = {"functions": [], "classes": [], "imports": [], "calls": [], "extends": []}
    extract_entities(tree.root_node, ext, entities, content)
    extract_calls_and_inheritance(tree.root_node, ext, entities, "", content)
    
    project_root = Path(root).resolve() if root else _find_project_root(path)
    ns = project_namespace(project_root)
    try:
        rel_posix = path.relative_to(project_root).as_posix()
    except ValueError:
        rel_posix = path.name

    file_id = f"File_{ns}/{rel_posix}"
    file_hash = hashlib.sha256(content).hexdigest()

    # Hash-skip: if the file content is unchanged since the last ingestion,
    # skip parsing and upserts entirely (keeps hook-driven re-ingests near-free).
    with get_connection(db_path) as conn:
        stored_hash = conn.execute(
            "SELECT json_extract(properties, '$.file_hash') FROM Nodes WHERE id = ? AND is_deleted = 0",
            (file_id,),
        ).fetchone()
    if stored_hash and stored_hash[0] == file_hash:
        return {"status": "unchanged", "file": str(path), "functions": 0, "classes": 0, "calls": 0, "extends": 0}

    # Clean up old edges and components before re-parsing
    pre_sweep_file_components(db_path, file_id)  # Soft-delete old component nodes
    pre_sweep_file_edges(db_path, file_id)  # Delete old CALLS/EXTENDS edges
    pre_sweep_file_imports(db_path, file_id)  # Delete old IMPORTS edges
    
    mtime = path.stat().st_mtime
    bindings = _collect_import_bindings(tree.root_node, ext, content)
    
    add_node(
        db_path, 
        file_id, 
        "Fact_Node", 
        {
            "entity_type": "File", 
            "path": rel_posix, 
            "abs_path": str(path),
            "project_root": str(project_root),
            "file_hash": file_hash, 
            "mtime": mtime,
            "bindings": bindings,
            "source": "AST"
        }, 
        trust_score=1.0, 
        verification_method="source_parse",
        agent_name=agent_name,
        rationale=rationale
    )
    
    for cls_data in entities["classes"]:
        cls_name = cls_data["name"]
        comp_id = f"Class_{cls_name}_{ns}/{rel_posix}"
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
                "file_path": rel_posix,
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
        comp_id = f"Func_{func_name}_{ns}/{rel_posix}"
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
                "file_path": rel_posix,
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
        sub_cls = f"Class_{ext_data['sub_class']}_{ns}/{rel_posix}"
        super_cls = f"Class_{ext_data['super_class']}_{ns}/{rel_posix}"
        add_node(db_path, super_cls, "Fact_Node", {"entity_type": "Component", "name": ext_data['super_class'], "component_type": "class", "source": "AST_Inheritance"}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
        add_relation(db_path, sub_cls, super_cls, "EXTENDS", trust_score=1.0, verification_method="source_parse")
        
    # One stub + one edge per unique callee name per file: repeated calls to the
    # same function collapse, and their receiver expressions merge into the
    # CALLS edge's "receivers" property (cross-file resolution input, v3.9.0).
    recv_by_callee = {}
    callers_by_callee = {}
    for call_data in entities["calls"]:
        recv_by_callee.setdefault(call_data["callee"], set()).add(call_data.get("receiver"))
        callers_by_callee.setdefault(call_data["callee"], set()).add(
            f"Func_{call_data['caller']}_{ns}/{rel_posix}")
    for callee_name, receivers in recv_by_callee.items():
        callee_id = f"Func_{callee_name}_{ns}/{rel_posix}"
        recv_list = sorted(r for r in receivers if r)
        add_node(db_path, callee_id, "Fact_Node", {"entity_type": "Component", "name": callee_name, "component_type": "function", "source": "AST_Call", "receivers": recv_list}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
        for caller_id in callers_by_callee[callee_name]:
            add_relation(db_path, caller_id, callee_id, "CALLS", props={"receivers": recv_list}, trust_score=1.0, verification_method="source_parse")
    
    # Process imports (create IMPORTS edges to Dependency nodes)
    for imp in set(entities["imports"]):
        clean_imp = sanitize_import_module(imp, ext)
        if not clean_imp:
            continue
        target_id = f"Dependency_{ns}/{clean_imp}"
        add_node(db_path, target_id, "Fact_Node", {"entity_type": "External_Dependency", "module": clean_imp, "created_by": agent_name, "source": "AST", "confidence": 1.0}, trust_score=0.8, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
        add_relation(db_path, file_id, target_id, "IMPORTS", trust_score=1.0, verification_method="source_parse")
    
    # Resolve cross-file CALLS edges to wire stubs to actual definitions
    _resolve_cross_file_calls(db_path, ns)
    
    return {"status": "success", "file": str(path), "functions": len(entities["functions"]), "classes": len(entities["classes"]), "calls": len(entities["calls"]), "extends": len(entities["extends"])}

def ingest_codebase(db_path: str, directory: str, agent_name: str = "Tree-sitter", rationale: str = "Full project AST ingestion", root: str = None):
    """Scans the directory, parses files, and builds the MOC graph with call graphs and inheritance.
    Pass `root` to pin the project namespace explicitly (monorepo-safe: guarantees
    ingest-code and ingest-file derive identical IDs even with nested project markers)."""
    init_db(db_path)
    directory = Path(directory).resolve()
    ns_base = Path(root).resolve() if root else directory
    ns = project_namespace(ns_base)
    print(f"[*] Starting AST ingestion of {directory} (namespace: {ns})")
    
    parsers = {}
    root_id = f"Project_{ns}"
    add_node(db_path, root_id, "Fact_Node", {"entity_type": "Project", "path": str(directory), "created_by": agent_name, "source": "AST", "confidence": 1.0}, trust_score=1.0, verification_method="source_parse", agent_name=agent_name, rationale=rationale)
    
    created_mocs = set()
    parsed_files = 0
    skipped_files = 0
    
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

        try:
            content = path.read_bytes()
            if b'\x00' in content[:1024]:
                print(f"[!] Skipping {path.name}: binary file detected.")
                continue
        except Exception as e:
            print(f"[!] Failed to read {path.name}: {e}")
            continue

        # Paths are keyed to the namespace root (monorepo-safe): ingest-code and
        # ingest_file derive identical IDs for the same file.
        try:
            rel_posix = path.relative_to(ns_base).as_posix()
            rel_dir = path.parent.relative_to(ns_base).as_posix()
        except ValueError:
            rel_posix = path.relative_to(directory).as_posix()
            rel_dir = path.parent.relative_to(directory).as_posix()
        file_id = f"File_{ns}/{rel_posix}"

        # Hash-skip: unchanged files skip parser loading, parsing, and all upserts.
        file_hash = hashlib.sha256(content).hexdigest()
        with get_connection(db_path) as conn:
            stored_hash = conn.execute(
                "SELECT json_extract(properties, '$.file_hash') FROM Nodes WHERE id = ? AND is_deleted = 0",
                (file_id,),
            ).fetchone()
        if stored_hash and stored_hash[0] == file_hash:
            skipped_files += 1
            continue

        if ext not in parsers:
            try:
                parsers[ext] = load_parser(ext)
            except ImportError as e:
                print(f"[!] {e}")
                return {"status": "error", "message": str(e)}

        parser = parsers[ext]
        if parser is None:
            continue

        try:
            tree = parser.parse(content)
        except Exception as e:
            print(f"[!] Failed to parse {path.name}: {e}")
            continue
        parsed_files += 1
            
        entities = {"functions": [], "classes": [], "imports": [], "calls": [], "extends": []}
        extract_entities(tree.root_node, ext, entities, content)
        extract_calls_and_inheritance(tree.root_node, ext, entities, "", content)

        moc_id = f"MOC_{ns}" if rel_dir in (".", "") else f"MOC_{ns}/{rel_dir}"
        batch_nodes = {}
        batch_edges = []
        if moc_id not in created_mocs:
            batch_nodes[moc_id] = {
                "id": moc_id, "label": "Fact_Node",
                "properties": {"entity_type": "MOC_Hub", "dir": rel_dir, "created_by": agent_name, "source": "AST", "confidence": 1.0},
                "trust_score": 1.0, "verification_method": "source_parse",
                "link_to": root_id, "link_type": "PART_OF",
            }
            created_mocs.add(moc_id)

        pre_sweep_file_components(db_path, file_id)
        pre_sweep_file_edges(db_path, file_id)  # Drop old CALLS/EXTENDS so receiver props can't go stale

        mtime = path.stat().st_mtime

        batch_nodes[file_id] = {
            "id": file_id, "label": "Fact_Node",
            "properties": {
                "entity_type": "File",
                "path": rel_posix,
                "abs_path": str(path),
                "project_root": str(directory),
                "file_hash": file_hash,
                "mtime": mtime,
                "bindings": _collect_import_bindings(tree.root_node, ext, content),
                "created_by": agent_name,
                "source": "AST",
                "confidence": 1.0,
            },
            "trust_score": 1.0, "verification_method": "source_parse",
            "link_to": moc_id, "link_type": "CONTAINS",
        }

        for cls_data in entities["classes"]:
            cls_name = cls_data["name"]
            comp_id = f"Class_{cls_name}_{ns}/{rel_posix}"
            batch_nodes[comp_id] = {
                "id": comp_id, "label": "Fact_Node",
                "properties": {
                    "entity_type": "Component",
                    "name": cls_name,
                    "component_type": "class",
                    "signature": cls_data["signature"],
                    "docstring": cls_data["docstring"],
                    "start_line": cls_data["start_line"],
                    "end_line": cls_data["end_line"],
                    "snippet": cls_data["snippet"],
                    "file_path": rel_posix,
                    "created_by": agent_name,
                    "source": "AST",
                    "confidence": 1.0,
                },
                "trust_score": 1.0, "verification_method": "source_parse",
                "link_to": file_id, "link_type": "DEFINED_IN",
            }

        for func_data in entities["functions"]:
            func_name = func_data["name"]
            comp_id = f"Func_{func_name}_{ns}/{rel_posix}"
            batch_nodes[comp_id] = {
                "id": comp_id, "label": "Fact_Node",
                "properties": {
                    "entity_type": "Component",
                    "name": func_name,
                    "component_type": "function",
                    "signature": func_data["signature"],
                    "docstring": func_data["docstring"],
                    "start_line": func_data["start_line"],
                    "end_line": func_data["end_line"],
                    "snippet": func_data["snippet"],
                    "file_path": rel_posix,
                    "created_by": agent_name,
                    "source": "AST",
                    "confidence": 1.0,
                },
                "trust_score": 1.0, "verification_method": "source_parse",
                "link_to": file_id, "link_type": "DEFINED_IN",
            }
        def _stub(spec_id, name, kind, receivers=None):
            # setdefault: a full definition spec already in the batch always wins
            # over a same-file stub, so source stays "AST".
            props = {"entity_type": "Component", "name": name, "component_type": kind, "source": "AST_Inheritance" if kind == "class" else "AST_Call"}
            if receivers is not None:
                props["receivers"] = receivers
            batch_nodes.setdefault(spec_id, {
                "id": spec_id, "label": "Fact_Node",
                "properties": props,
                "trust_score": 0.8, "verification_method": "source_parse",
            })

        for ext_data in entities["extends"]:
            sub_cls = f"Class_{ext_data['sub_class']}_{ns}/{rel_posix}"
            super_cls = f"Class_{ext_data['super_class']}_{ns}/{rel_posix}"
            _stub(sub_cls, ext_data["sub_class"], "class")
            _stub(super_cls, ext_data["super_class"], "class")
            batch_edges.append({"source_id": sub_cls, "target_id": super_cls, "relation_type": "EXTENDS", "trust_score": 1.0, "verification_method": "source_parse"})

        # Unique callees only: one stub per (callee, file), receiver sets merged.
        # pre_sweep_file_edges has already dropped this file's CALLS edges, so a
        # callee whose receivers were all removed lands with receivers: [].
        recv_sets = {}
        for call_data in entities["calls"]:
            recv_sets.setdefault(call_data["callee"], set()).add(call_data.get("receiver"))
        for callee_name, receivers in recv_sets.items():
            callee_id = f"Func_{callee_name}_{ns}/{rel_posix}"
            _stub(callee_id, callee_name, "function", receivers=sorted(r for r in receivers if r))
        for call_data in entities["calls"]:
            caller_id = f"Func_{call_data['caller']}_{ns}/{rel_posix}"
            callee_id = f"Func_{call_data['callee']}_{ns}/{rel_posix}"
            _stub(caller_id, call_data["caller"], "function")
            batch_edges.append({
                "source_id": caller_id, "target_id": callee_id, "relation_type": "CALLS",
                "properties": {"receivers": sorted(r for r in recv_sets[call_data["callee"]] if r)},
                "trust_score": 1.0, "verification_method": "source_parse",
            })

        pre_sweep_file_imports(db_path, file_id)
        for imp in set(entities["imports"]):
            clean_imp = sanitize_import_module(imp, ext)
            if not clean_imp:
                continue
            target_id = f"Dependency_{ns}/{clean_imp}"
            batch_nodes[target_id] = {
                "id": target_id, "label": "Fact_Node",
                "properties": {"entity_type": "External_Dependency", "module": clean_imp, "created_by": agent_name, "source": "AST", "confidence": 1.0},
                "trust_score": 0.8, "verification_method": "source_parse",
                "link_to": root_id, "link_type": "USES",
            }
            batch_edges.append({"source_id": file_id, "target_id": target_id, "relation_type": "IMPORTS", "trust_score": 1.0, "verification_method": "source_parse"})

        # One connection + one transaction per file instead of one per node.
        bulk_upsert_nodes(db_path, list(batch_nodes.values()), batch_edges, agent_name=agent_name, rationale=rationale)

    rewired = _resolve_cross_file_calls(db_path, ns)
    print(f"[*] AST Ingestion Complete! (parsed: {parsed_files}, hash-skipped: {skipped_files}, cross-file calls resolved: {rewired})")
    return {"status": "success", "parsed": parsed_files, "skipped": skipped_files, "calls_resolved": rewired}


def _module_to_files(mod: str, level: int, caller_rel: str, ext: str, local_hint: str = None):
    """Candidate repo-relative paths a bound module could live at (ordered).

    Empty `mod` with level>0 (`from . import x`) uses `local_hint` (the bound
    name) as the module file. Rust `crate::`/`super::` paths are mapped
    best-effort; Go module paths are always external (no candidates).
    """
    def py_candidates(base: str, dotted: str):
        seg = dotted.replace(".", "/")
        stem = f"{base}/{seg}" if base else seg
        if not dotted:
            return []
        return [f"{stem}.py", f"{stem}/__init__.py"]

    if ext == ".py":
        if level > 0:
            parts = caller_rel.split("/")[:-1]
            parts = parts[: len(parts) - (level - 1)] if level > 1 else parts
            base = "/".join(parts)
            if not mod and local_hint:
                return py_candidates(base, local_hint) + py_candidates(base, mod)
            return py_candidates(base, mod)
        return py_candidates("", mod)
    if ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        if not mod.startswith("."):
            return []  # bare specifier: package, external
        parts = caller_rel.split("/")[:-1]
        segs = mod.split("/")
        while segs and segs[0] == "..":
            segs.pop(0)
            if parts:
                parts.pop()
        if segs and segs[0] == ".":
            segs.pop(0)
        stem = "/".join(parts + segs)
        out = [stem]
        for sfx in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts"):
            out.append(stem + sfx)
            out.append(stem + "/index" + sfx)
        return out
    if ext == ".rs":
        segs = mod.split("::") if mod else []
        if segs and segs[0] in ("crate", "super", "self"):
            head = segs[0]
            rest = "/".join(segs[1:])
            out = []
            if rest:
                if head == "crate":
                    out += [f"src/{rest}.rs", f"src/{rest}/mod.rs"]
                else:
                    parts = caller_rel.split("/")[:-1]
                    if head == "super" and parts:
                        parts.pop()
                    base = "/".join(parts)
                    stem = f"{base}/{rest}" if base else rest
                    out += [f"{stem}.rs", f"{stem}/mod.rs"]
            return out
        return []
    return []


def _resolve_cross_file_calls(db_path: str, ns: str) -> int:
    """
    Post-pass: CALLS edges initially point at same-file stubs. This pass rewires
    them to real targets, receiver-aware (v3.9.0):

    1. Attributed call `recv.name()`: the caller file's import bindings resolve
       the receiver root. A binding to an in-project module resolves `name`
       inside that file (scope-aware — no more cross-linking two files'
       same-named functions through a member call). A binding to an external
       module rewires to a synthetic member node `Dependency_{ns}/<dotted>`,
       so numpy.dot lands on numpy, not on an in-project `dot`.
    2. Bare `name()`: an absolute external binding for the name wins over the
       in-project unique-name rule (`from json import loads; loads()` is json's,
       not the one project function called `loads`).
    3. Fallback: uniquely-named in-project definition (v3.7.0 behavior).

    Stubs that resolve to nothing keep their edges; edge-less stubs are
    hard-deleted. Rewired edges carry `resolved_by` for audit.
    """
    ns_token = f"_{ns}/"
    file_prefix = f"File_{ns}/"
    now_fn = now_iso
    with get_connection(db_path) as conn:
        # --- Registry: files (rel -> id, bindings), defs (global + per file) ---
        files = {}      # rel_posix -> file_id
        bindings_by_file = {}  # file_id -> {local: binding}
        for fid, rel, bl in conn.execute(
            "SELECT id, json_extract(properties, '$.path'), json_extract(properties, '$.bindings') "
            "FROM Nodes WHERE json_extract(properties, '$.entity_type') = 'File' "
            "AND is_deleted = 0 AND id LIKE ?",
            (f"File_{ns}/%",),
        ).fetchall():
            if rel:
                files[rel] = fid
            if bl:
                try:
                    bindings_by_file[fid] = json.loads(bl)
                except Exception:
                    bindings_by_file[fid] = {}

        # Definitions: DEFINED_IN edges give (def_id -> file_id); props give name.
        defs_by_name = {}     # name -> [def_id]
        defs_in_file = {}     # (file_id, name) -> def_id
        def_files = dict(conn.execute(
            "SELECT source_id, target_id FROM Edges WHERE relation_type = 'DEFINED_IN'"
        ).fetchall())
        defined_ids = set(def_files)
        def_ids = [d for d in def_files if d.startswith("Func_") and ns_token in d]
        for i in range(0, len(def_ids), 500):
            chunk = def_ids[i:i + 500]
            ph = ",".join("?" * len(chunk))
            for did, props in conn.execute(
                f"SELECT id, properties FROM Nodes WHERE id IN ({ph}) AND is_deleted = 0", chunk
            ).fetchall():
                name = json.loads(props).get("name") if props else None
                if not name:
                    continue
                defs_by_name.setdefault(name, []).append(did)
                defs_in_file.setdefault((def_files[did], name), did)

        # Stub CALLS edges: target has no DEFINED_IN.
        stub_edges = []
        for src, tgt, props in conn.execute("""
            SELECT e.source_id, e.target_id, e.properties FROM Edges e
            JOIN Nodes n ON n.id = e.target_id
            WHERE e.relation_type = 'CALLS'
              AND n.is_deleted = 0
              AND e.target_id NOT IN (SELECT source_id FROM Edges WHERE relation_type = 'DEFINED_IN')
        """).fetchall():
            if tgt.startswith("Func_") and ns_token in tgt and src.startswith("Func_") and ns_token in src:
                stub_edges.append((src, tgt, props))

        stub_names = {}
        stub_ids = {t for _, t, _ in stub_edges}
        if stub_ids:
            stub_list = list(stub_ids)
            for i in range(0, len(stub_list), 500):
                chunk = stub_list[i:i + 500]
                ph = ",".join("?" * len(chunk))
                for sid, props in conn.execute(
                    f"SELECT id, properties FROM Nodes WHERE id IN ({ph})", chunk
                ).fetchall():
                    stub_names[sid] = json.loads(props).get("name") if props else None

        def _dotted_base(b):
            """Full dotted module for a binding: `import a.b as c` -> a.b,
            `from a.b import c` -> a.b.c, `from json import loads` -> json.loads."""
            mod = b.get("module", "")
            orig = b.get("orig")
            if not orig or orig in ("*", "default") or orig == mod or (mod and orig.startswith(mod + ".")):
                return mod
            return f"{mod}.{orig}" if mod else orig

        def _in_bound_file(b, name, caller_file_rel, ext):
            """Def lookup for a binding that points at an in-project file.
            For `from . import x` (empty module) the bound orig names the module file."""
            hint = b.get("orig") or name
            for cand in _module_to_files(b.get("module", ""), b.get("level", 0), caller_file_rel, ext, local_hint=hint):
                if cand in files:
                    hit = defs_in_file.get((files[cand], name))
                    if hit:
                        return hit
            return None

        def resolve(name, recv, caller_file_rel, bindings):
            """-> (target_id, method, external_dotted) or None (keep stub)."""
            ext = Path(caller_file_rel).suffix if caller_file_rel else ""
            if recv:
                root = recv.split(".")[0].strip("()[]") or recv
                b = bindings.get(root)
                if b is None:
                    return _unique(name)  # local instance / unbound receiver: legacy rule
                level = b.get("level", 0)
                if level > 0 or (ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs")
                                 and str(b.get("module", "")).startswith((".", "crate::", "super::", "self::"))):
                    hit = _in_bound_file(b, name, caller_file_rel, ext)
                    if hit:
                        return hit, "receiver", None
                    return _unique(name)
                mod = b.get("module", "")
                if mod:
                    cands = _module_to_files(mod, 0, caller_file_rel, ext)
                    if any(c in files for c in cands):
                        hit = _in_bound_file(b, name, caller_file_rel, ext)
                        if hit:
                            return hit, "receiver", None
                        return _unique(name)
                    if cands or not mod.startswith("."):
                        rest = recv[len(root):]  # chained segments beyond the root
                        dotted = _dotted_base(b) + rest + "." + name
                        return f"Dependency_{ns}/{dotted}", "receiver_external", dotted
                    return None
                return _unique(name)
            # Bare call: an external module binding for the name wins over the
            # in-project unique-name rule (`from json import loads; loads()`).
            b = bindings.get(name)
            if b and b.get("level", 0) > 0:
                hit = _in_bound_file(b, name, caller_file_rel, ext)
                if hit:
                    return hit, "relative_binding", None
            elif b and b.get("level", 0) == 0 and b.get("module"):
                cands = _module_to_files(b["module"], 0, caller_file_rel, ext)
                if any(c in files for c in cands):
                    hit = _in_bound_file(b, name, caller_file_rel, ext)
                    if hit:
                        return hit, "module_binding", None
                elif cands or not str(b["module"]).startswith("."):
                    dotted = _dotted_base(b)
                    if dotted:
                        return f"Dependency_{ns}/{dotted}", "external_binding", dotted
            return _unique(name)

        def _unique(name):
            cands = defs_by_name.get(name, [])
            if len(cands) == 1:
                return cands[0], "unique_name", None
            return None

        rewired = 0
        with write_transaction(conn):
            for caller, stub_id, eprops in stub_edges:
                name = stub_names.get(stub_id)
                if not name:
                    continue
                try:
                    old_props = json.loads(eprops) if eprops else {}
                except Exception:
                    old_props = {}
                callers_rel = caller.split(ns_token, 1)[1]
                bindings = bindings_by_file.get(file_prefix + callers_rel) or {}
                receivers = [r for r in (old_props.get("receivers") or []) if r] or [None]
                targets = {}
                unresolved = 0
                for recv in receivers:
                    hit = resolve(name, recv, callers_rel, bindings)
                    if hit:
                        targets[hit[0]] = hit
                    else:
                        unresolved += 1
                full = targets and not unresolved and len(targets) == 1
                for target, (_t, method, dotted) in targets.items():
                    if dotted:
                        conn.execute(
                            "INSERT INTO Nodes (id, label, properties, created_at, last_verified_at, updated_at, trust_score, verification_method) "
                            "VALUES (?, 'Fact_Node', ?, ?, ?, ?, 0.8, 'source_parse') ON CONFLICT(id) DO NOTHING",
                            (target, json.dumps({"entity_type": "External_Dependency", "module": dotted, "source": "AST_Call_Member"}), now_fn(), now_fn(), now_fn()),
                        )
                    new_props = dict(old_props)
                    new_props["resolved_by"] = method
                    conn.execute("""
                        INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at, last_verified_at, trust_score, verification_method)
                        VALUES (?, ?, 'CALLS', ?, ?, ?, 1.0, 'source_parse')
                        ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                            last_verified_at = excluded.last_verified_at,
                            properties = CASE WHEN excluded.properties = '{}' THEN Edges.properties ELSE excluded.properties END
                    """, (caller, target, json.dumps(new_props), now_fn(), now_fn()))
                if not full:
                    # Unresolved or split across receivers: keep the stub edge —
                    # it documents the ambiguity a wrong edge would hide.
                    continue
                target = next(iter(targets))
                conn.execute("DELETE FROM Edges WHERE source_id = ? AND target_id = ? AND relation_type = 'CALLS'", (caller, stub_id))
                leftover = conn.execute(
                    "SELECT 1 FROM Edges WHERE (source_id = ? OR target_id = ?) AND relation_type = 'CALLS' LIMIT 1",
                    (stub_id, stub_id),
                ).fetchone()
                if not leftover and stub_id not in defined_ids:
                    conn.execute("DELETE FROM Nodes WHERE id = ?", (stub_id,))
                rewired += 1
    return rewired
