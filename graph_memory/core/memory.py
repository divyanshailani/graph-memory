import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from graph_memory.core.engine import (
    get_or_create_node as add_node,
    get_connection,
    query_decision_ledger,
    now_iso
)
from graph_memory.core.knowledge import format_yaml_frontmatter

MEMORY_CATEGORIES = [
    "common_pitfalls_experience",
    "development_test_specification",
    "project_environment_configuration",
    "project_tech_stack",
    "project_introduction"
]

# Category -> keywords matched against Decision_Ledger rationale/action text.
# Reflection is data-driven: each memory card digests REAL recent decisions.
CATEGORY_KEYWORDS = {
    "common_pitfalls_experience": ["fix", "bug", "error", "crash", "regression", "pitfall", "collision", "failure"],
    "development_test_specification": ["test", "pytest", "suite", "regression gate", "compile"],
    "project_environment_configuration": ["config", "env", "hook", "path", "cross-platform", "windows", "macos", "linux", "install"],
    "project_tech_stack": ["sqlite", "fts", "tree-sitter", "parser", "mcp", "pypi", "dependency", "schema", "transport"],
    "project_introduction": [],  # introduction always includes graph stats
}

STATIC_INVARIANTS = {
    "common_pitfalls_experience": [
        "Avoid hardcoded path assumptions across macOS, Windows, and Linux.",
    ],
    "development_test_specification": [
        "All release features require 100% test suite execution via `pytest`.",
    ],
    "project_environment_configuration": [
        "Environment-driven configuration via `GRAPH_MEMORY_DB_PATH` and `GRAPH_MEMORY_HTTP_HOST/PORT`.",
    ],
    "project_tech_stack": [
        "SQLite local engine, tree-sitter AST parsers, PyPI distribution, MCP Server (stdio + streamable HTTP).",
    ],
    "project_introduction": [],
}

def _graph_stats(db_path: str) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        nodes = conn.execute("SELECT COUNT(*) FROM Nodes WHERE is_deleted = 0").fetchone()[0]
        edges = conn.execute("SELECT COUNT(*) FROM Edges").fetchone()[0]
        agents = [r[0] for r in conn.execute(
            "SELECT agent_name, COUNT(*) c FROM Decision_Ledger GROUP BY agent_name ORDER BY c DESC LIMIT 5"
        ).fetchall()]
    return {"nodes": nodes, "edges": edges, "top_agents": agents}

def _match_decisions(decisions: list, category: str, limit: int = 5) -> list:
    keywords = CATEGORY_KEYWORDS.get(category) or []
    if not keywords:
        return decisions[:limit]
    matched = []
    for d in decisions:
        hay = f"{d.get('action', '')} {d.get('rationale', '')}".lower()
        if any(k in hay for k in keywords):
            matched.append(d)
    return matched[:limit]

def reflect_session_memory(db_path: str, target_dir: str, agent_name: str = "Memory-Reflect") -> Dict[str, Any]:
    """
    Reflects REAL history into memory cards: digests the last 30 days of the
    Decision_Ledger (agent, action, rationale) into the 5 standardized memory
    categories under target_dir/memories/, plus live graph statistics. Static
    invariants are kept only as verified baseline facts — everything else is
    derived from actual data.
    """
    mem_path = Path(target_dir).resolve() / "memories"
    mem_path.mkdir(parents=True, exist_ok=True)

    timestamp = now_iso()
    decisions = query_decision_ledger(db_path, days=30, limit=100)
    stats = _graph_stats(db_path)

    created_memories = []
    for category in MEMORY_CATEGORIES:
        cat_dir = mem_path / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        title = f"{category.replace('_', ' ').title()}"
        mem_file = cat_dir / f"{category}.md"

        frontmatter = {
            "kind": "project_memory",
            "category": category,
            "title": title,
            "updated_at": timestamp
        }

        body = f"# Memory: {title}\n\n"
        body += "## Overview & Learned Invariants\n\n"
        body += f"- Active graph: {stats['nodes']} nodes, {stats['edges']} edges. Frequent decision agents: {', '.join(stats['top_agents']) or 'none'}.\n"
        for inv in STATIC_INVARIANTS.get(category, []):
            body += f"- {inv}\n"

        matched = _match_decisions(decisions, category)
        body += "\n## Reflected from Decision Ledger (last 30 days)\n\n"
        if matched:
            for d in matched:
                body += f"- **[{d['agent_name']}]** {d['action']} on `{d['node_id']}`: {d['rationale'][:120]}\n"
        else:
            body += "- No recent decisions matched this category.\n"

        content = format_yaml_frontmatter(frontmatter) + body
        mem_file.write_text(content, encoding="utf-8")

        node_mem_id = f"Memory_{category}"
        add_node(
            db_path,
            node_mem_id,
            "Memory_Node",
            {
                "kind": "project_memory",
                "category": category,
                "title": title,
                "file_path": str(mem_file),
                "created_by": agent_name,
                "source": "Memory-Reflect"
            },
            trust_score=1.0,
            verification_method="source_parse",
            agent_name=agent_name
        )
        created_memories.append(str(mem_file))

    return {"status": "success", "memories_count": len(created_memories), "decisions_reflected": len(decisions), "files": created_memories}
