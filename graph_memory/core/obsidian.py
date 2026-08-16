"""
Obsidian vault export (v3.6.0 "Open Borders").

Exports the curated knowledge graph (everything except mechanical AST nodes) as
an Obsidian vault: one note per node with YAML frontmatter, observations as
bullet lists, and graph edges rendered as [[Wikilinks]] — so exported memory is
browsable and clickable inside the knowledge tool people already live in.
"""
import json
import re
from pathlib import Path

from graph_memory.core.engine import get_connection

# Mechanical AST entity types stay out of the vault — they belong to the code graph.
_AST_ENTITY_TYPES = {"Component", "File", "MOC_Hub", "External_Dependency", "Project"}


def _note_filename(node_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_\-.]+", "_", node_id).strip("_")
    return safe or "untitled"


def export_obsidian_vault(db_path: str, vault_dir: str) -> dict:
    """Writes curated nodes as markdown notes with [[wikilinks]] for graph edges."""
    vault = Path(vault_dir)
    vault.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        nodes = conn.execute(
            "SELECT id, label, properties, trust_score, last_verified_at "
            "FROM Nodes WHERE is_deleted = 0"
        ).fetchall()
        edges = conn.execute(
            "SELECT source_id, target_id, relation_type FROM Edges"
        ).fetchall()

    exported_ids = {}
    for node_id, label, props_json, trust, verified in nodes:
        props = json.loads(props_json) if props_json else {}
        if props.get("entity_type") in _AST_ENTITY_TYPES:
            continue
        exported_ids[node_id] = _note_filename(node_id)

    edge_map = {nid: [] for nid in exported_ids}
    for source, target, rel_type in edges:
        if source in exported_ids and target in exported_ids:
            edge_map[source].append((rel_type, target))
            edge_map[target].append((rel_type, source, "incoming"))

    files_written = 0
    links_written = 0
    for node_id, label, props_json, trust, verified in nodes:
        if node_id not in exported_ids:
            continue
        props = json.loads(props_json) if props_json else {}
        fname = exported_ids[node_id]

        frontmatter_lines = [
            "---",
            f"id: \"{node_id}\"",
            f"label: \"{label}\"",
            f"trust: {trust if trust is not None else 1.0}",
            f"verified: \"{verified or ''}\"",
            f"source: \"{props.get('source', '')}\"",
            "---",
        ]

        body = [f"# {props.get('name') or props.get('description') or node_id}", ""]

        description = props.get("description")
        if description and description != (props.get("name") or node_id):
            body += [str(description), ""]
        summary = props.get("summary")
        if summary:
            body += [f"> {summary}", ""]

        observations = props.get("observations") or []
        if observations:
            body.append("## Observations")
            body += [f"- {o}" for o in observations]
            body.append("")

        rationale = props.get("rationale")
        if rationale:
            body += ["## Rationale", str(rationale), ""]

        relations = edge_map.get(node_id, [])
        if relations:
            body.append("## Links")
            seen = set()
            for rel in relations:
                if len(rel) == 2:
                    rel_type, target = rel
                    key = (rel_type, target, "outgoing")
                else:
                    rel_type, target, direction = rel
                    key = (rel_type, target, direction)
                if key in seen:
                    continue
                seen.add(key)
                body.append(
                    f"- {'←' if key[2] == 'incoming' else '→'} [[{exported_ids[target]}]] ({key[0]})"
                )
                links_written += 1
            body.append("")

        note_path = vault / f"{fname}.md"
        note_path.write_text("\n".join(frontmatter_lines) + "\n" + "\n".join(body), encoding="utf-8")
        files_written += 1

    return {
        "status": "success",
        "vault_dir": str(vault),
        "notes_written": files_written,
        "links_written": links_written,
    }
