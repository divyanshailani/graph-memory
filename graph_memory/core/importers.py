"""
Memory importers (v3.6.0 "Open Borders").

Adoption is a migration problem — these importers make switching to Graph Memory
zero-cost from the formats people already have on disk:

- Markdown memory files (CLAUDE.md, AGENTS.md, .cursorrules, any .md):
  each `##`-section becomes a Knowledge_Node linked to a document node,
  with bullet lines preserved as observations.
- mem0 JSON exports (list of {"id", "memory", ...} or {"results": [...]}):
  each memory record becomes a Fact_Node.
"""
import hashlib
import json
import re
from pathlib import Path

from graph_memory.core.engine import get_or_create_node, create_relation

_AST_ENTITY_TYPES = {"Component", "File", "MOC_Hub", "External_Dependency", "Project"}


def _slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return (slug[:max_len].rstrip("_")) or "untitled"


def import_markdown_file(db_path: str, file_path: str, agent_name: str = "Importer") -> dict:
    """
    Imports a markdown memory file (CLAUDE.md, AGENTS.md, .cursorrules, any .md)
    into the graph: one document node + one Knowledge_Node per section heading,
    with bullet observations preserved. Idempotent (stable node IDs from slugs).
    """
    path = Path(file_path)
    if not path.is_file():
        return {"status": "error", "message": f"File '{file_path}' not found."}

    content = path.read_text(encoding="utf-8", errors="ignore")
    stem = _slug(path.stem)
    source = "markdown_import"
    if path.name.lower() in ("claude.md",):
        source = "claude_md_import"
    elif path.name.lower() == ".cursorrules":
        source = "cursorrules_import"
    elif path.name.lower() == "agents.md":
        source = "agents_md_import"

    doc_id = f"Import_Doc_{stem}"
    get_or_create_node(
        db_path, doc_id, "Knowledge_Node",
        {
            "entity_type": "Imported_Document",
            "description": f"Imported memory document: {path.name}",
            "source": source,
            "file_path": str(path),
        },
        trust_score=0.9, verification_method="import",
        agent_name=agent_name, rationale=f"Imported from {path.name}",
    )

    # Split into sections by markdown headings (## .. ####; H1 is the doc title).
    sections = []
    current_heading, current_lines = None, []
    for line in content.splitlines():
        heading_match = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading_match:
            if current_heading and any(l.strip() for l in current_lines):
                sections.append((current_heading, current_lines))
            current_heading, current_lines = heading_match.group(2).strip(), []
        else:
            current_lines.append(line)
    if current_heading and any(l.strip() for l in current_lines):
        sections.append((current_heading, current_lines))

    # No headings: treat the whole file as one section.
    if not sections:
        sections = [(path.stem, content.splitlines())]

    imported = 0
    for heading, lines in sections:
        bullets = [
            re.sub(r"^[\-\*\d\.]+\s*", "", l.strip()).strip()
            for l in lines
            if l.strip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5."))
        ]
        bullets = [b for b in bullets if b][:20]
        summary_text = " ".join(l.strip() for l in lines if l.strip())[:200]

        section_id = f"Import_MD_{stem}_{_slug(heading)}"
        get_or_create_node(
            db_path, section_id, "Knowledge_Node",
            {
                "entity_type": "Imported_Section",
                "description": heading,
                "summary": summary_text,
                "observations": bullets,
                "source": source,
                "file_path": str(path),
            },
            trust_score=0.9, verification_method="import",
            link_to=doc_id, link_type="PART_OF",
            agent_name=agent_name, rationale=f"Section '{heading}' from {path.name}",
        )
        imported += 1

    return {"status": "success", "file": str(path), "sections_imported": imported, "doc_node": doc_id}


def import_mem0(db_path: str, json_path: str, agent_name: str = "Importer") -> dict:
    """
    Imports a mem0 JSON export. Accepts either a bare list of memory records or
    {"results": [...]} / {"memories": [...]} wrappers. Each record's "memory"
    (or "data"/"text") field becomes a Fact_Node with a stable ID.
    """
    path = Path(json_path)
    if not path.is_file():
        return {"status": "error", "message": f"File '{json_path}' not found."}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    if isinstance(data, dict):
        records = data.get("results") or data.get("memories") or []
    else:
        records = data
    if not isinstance(records, list):
        return {"status": "error", "message": "Expected a JSON list or {'results': [...]} object."}

    imported = 0
    for record in records:
        if not isinstance(record, dict):
            record = {"memory": str(record)}
        text = record.get("memory") or record.get("data") or record.get("text")
        if not text:
            continue
        record_key = record.get("id") or _slug(text, 32) or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        node_id = f"Import_Mem0_{_slug(str(record_key), 32)}"
        props = {
            "entity_type": "Imported_Memory",
            "description": text,
            "source": "mem0_import",
        }
        for meta_key in ("user_id", "agent_id", "run_id"):
            if record.get(meta_key):
                props[meta_key] = str(record[meta_key])
        get_or_create_node(
            db_path, node_id, "Fact_Node", props,
            trust_score=0.9, verification_method="import",
            agent_name=agent_name, rationale="Imported from mem0 export",
        )
        imported += 1

    return {"status": "success", "file": str(path), "memories_imported": imported}
