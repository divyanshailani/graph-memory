import os
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from graph_memory.core.engine import (
    get_or_create_node as add_node,
    create_relation as add_relation,
    get_connection,
    now_iso
)

KNOWLEDGE_CATEGORIES = [
    "frontend_style",
    "backend_architecture",
    "build_system",
    "logging_system",
    "configuration_system",
    "dependency_management",
    "error_handling",
    "external_dependency",
    "business_term"
]

def format_yaml_frontmatter(metadata: Dict[str, Any]) -> str:
    """Formats a dictionary into YAML frontmatter string."""
    lines = ["---"]
    for k, v in metadata.items():
        if isinstance(v, list):
            items_str = ", ".join([f'"{item}"' for item in v])
            lines.append(f"{k}: [{items_str}]")
        elif isinstance(v, (int, float, bool)):
            lines.append(f"{k}: {str(v).lower()}")
        else:
            lines.append(f'{k}: "{v}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"

def extract_knowledge_cards(db_path: str, target_dir: str, agent_name: str = "Knowledge-Engine") -> Dict[str, Any]:
    """
    Scans the SQLite graph memory database and generates domain Knowledge Cards under target_dir/repo-knowledge/.
    Classifies component/file facts into 8 standardized software knowledge domains.
    """
    target_path = Path(target_dir).resolve() / "repo-knowledge"
    target_path.mkdir(parents=True, exist_ok=True)
    
    cards_created = []
    
    with get_connection(db_path) as conn:
        # Fetch all active file and component nodes
        cursor = conn.execute("""
            SELECT id, label, properties, trust_score 
            FROM Nodes 
            WHERE is_deleted = 0 AND label IN ('Fact_Node', 'Component_Node', 'Package_Node')
        """)
        nodes = cursor.fetchall()

    category_buckets: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in KNOWLEDGE_CATEGORIES}
    
    for node_id, label, meta_str, trust in nodes:
        meta = json.loads(meta_str) if meta_str else {}
        entity_type = meta.get("entity_type", "")
        file_path = meta.get("file_path") or meta.get("path", "")
        name = meta.get("name", node_id)
        
        # Heuristic Domain Classification
        lower_path = file_path.lower()
        lower_name = name.lower()
        
        if any(term in lower_path for term in ["frontend", "ui", "css", "component", "tailwind", "layout", "page.tsx"]):
            category_buckets["frontend_style"].append(meta)
        elif any(term in lower_path for term in ["docker", "pypi", "pyproject.toml", "package.json", "setup.py", "build"]):
            category_buckets["build_system"].append(meta)
        elif any(term in lower_path for term in ["log", "telemetry", "trace", "logging"]):
            category_buckets["logging_system"].append(meta)
        elif any(term in lower_path for term in ["env", "config", "setting", "flag"]):
            category_buckets["configuration_system"].append(meta)
        elif any(term in lower_path for term in ["api", "router", "server", "engine", "mcp", "core"]):
            category_buckets["backend_architecture"].append(meta)
        elif entity_type == "External_Dependency":
            category_buckets["external_dependency"].append(meta)
            
    # Write Category Markdown Cards
    timestamp = now_iso()
    index_rows = []
    
    for category, bucket in category_buckets.items():
        if not bucket:
            continue
            
        cat_dir = target_path / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        card_file = cat_dir / f"{category}.md"
        
        title = f"{category.replace('_', ' ').title()} Overview"
        frontmatter = {
            "kind": "repo_knowledge",
            "category": category,
            "title": title,
            "scopes": ["**"],
            "updated_at": timestamp
        }
        
        body = f"# {title}\n\n## What system/approach is used\n\n"
        body += f"Auto-extracted knowledge domain summary covering {len(bucket)} architectural components and files.\n\n"
        body += "## Key files and packages\n\n"
        
        seen_files = set()
        for item in bucket[:20]:
            fpath = item.get("file_path") or item.get("path")
            if fpath and fpath not in seen_files:
                seen_files.add(fpath)
                body += f"- `{fpath}` — {item.get('docstring') or item.get('signature') or 'Project component'}\n"
                
        body += "\n## Architecture and conventions\n\n"
        body += f"Centralized conventions governing {category.replace('_', ' ')} logic within the codebase.\n\n"
        
        card_content = format_yaml_frontmatter(frontmatter) + body
        card_file.write_text(card_content, encoding="utf-8")
        
        node_card_id = f"Knowledge_{category}"
        add_node(
            db_path,
            node_card_id,
            "Knowledge_Node",
            {
                "kind": "repo_knowledge",
                "category": category,
                "title": title,
                "file_path": str(card_file),
                "created_by": agent_name,
                "source": "Knowledge-Engine"
            },
            trust_score=1.0,
            verification_method="source_parse",
            agent_name=agent_name
        )
        
        cards_created.append(str(card_file))
        index_rows.append(f"| {category.replace('_', ' ').title()} | {title} | 1.00 |")

    # Top-Level index.md for repo-knowledge
    index_file = target_path / "index.md"
    index_frontmatter = {
        "layout_version": "agent/v1",
        "kind": "repo_knowledge",
        "generated_at": timestamp
    }
    
    index_content = format_yaml_frontmatter(index_frontmatter)
    index_content += "# Repository-Level Knowledge Cards\n\n"
    index_content += "| Category | Title | Confidence |\n|---|---|---|\n"
    index_content += "\n".join(index_rows) + "\n"
    index_file.write_text(index_content, encoding="utf-8")
    
    return {"status": "success", "cards_count": len(cards_created), "index_file": str(index_file), "cards": cards_created}

def generate_repo_wiki(db_path: str, target_dir: str, repo_name: str = "Project", branch: str = "main", commit_hash: str = "head", agent_name: str = "Wiki-Engine") -> Dict[str, Any]:
    """
    Generates a hierarchical Markdown Repo Wiki under target_dir/codebase/ matching Qoder's exact schema.
    Includes index.md, module READMEs, and relations (Depends on / Depended on by / Related).
    """
    codebase_path = Path(target_dir).resolve() / "codebase"
    codebase_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = now_iso()
    
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT id, properties FROM Nodes WHERE label = 'Fact_Node' AND is_deleted = 0
        """)
        nodes = cursor.fetchall()
        
    modules: Dict[str, List[Dict[str, Any]]] = {}
    for node_id, meta_str in nodes:
        meta = json.loads(meta_str) if meta_str else {}
        entity_type = meta.get("entity_type")
        if entity_type == "MOC_Hub":
            dir_name = meta.get("dir", "Core")
            if dir_name not in modules:
                modules[dir_name] = []
        elif entity_type == "File":
            fpath = meta.get("path", "")
            parent_dir = str(Path(fpath).parent)
            if parent_dir not in modules:
                modules[parent_dir] = []
            modules[parent_dir].append(meta)
            
    created_wiki_files = []
    hierarchy_links = []
    
    for mod_dir, files in modules.items():
        clean_dir = "Root" if mod_dir in [".", ""] else mod_dir.replace("/", "_")
        mod_folder = codebase_path / clean_dir
        mod_folder.mkdir(parents=True, exist_ok=True)
        
        mod_readme = mod_folder / "README.md"
        mod_id = f"mod_{clean_dir.lower()}"
        
        mod_frontmatter = {
            "description": f"Architectural subsystem module for {clean_dir}",
            "module_id": mod_id,
            "source_files": [f.get("path") for f in files if f.get("path")][:10],
            "updated_at": timestamp
        }
        
        mod_body = f"# Subsystem Module: {clean_dir}\n\n"
        mod_body += "## What system/approach is used\n\n"
        mod_body += f"Handles modular logic for `{clean_dir}` components within the project graph.\n\n"
        mod_body += "## Key files and packages\n\n"
        for f in files[:10]:
            mod_body += f"- `{f.get('path')}` — SHA256: `{f.get('file_hash', 'N/A')[:8]}`\n"
            
        mod_body += "\n## Architecture and conventions\n\n"
        mod_body += "Strict adherence to modular single-responsibility design patterns.\n\n"
        mod_body += "## Relations\n\n"
        mod_body += "- **Depends on**: None\n- **Depended on by**: Project Core\n- **Related**: Core AST Ingesters\n"
        
        content = format_yaml_frontmatter(mod_frontmatter) + mod_body
        mod_readme.write_text(content, encoding="utf-8")
        created_wiki_files.append(str(mod_readme))
        
        hierarchy_links.append(f"- [{clean_dir}](<{clean_dir}/README.md>) — Module for `{clean_dir}` containing {len(files)} files.")

    # Top-Level Index.md
    top_index = codebase_path / "index.md"
    top_frontmatter = {
        "layout_version": "agent/v1",
        "store_schema_version": "v1alpha1",
        "title": f"{repo_name} codebase knowledge",
        "repo": repo_name,
        "branch": branch,
        "commit": commit_hash,
        "source": "codebase",
        "generated_at": timestamp,
        "module_count": len(modules)
    }
    
    top_content = format_yaml_frontmatter(top_frontmatter)
    top_content += f"# {repo_name} Codebase Knowledge Wiki\n\n"
    top_content += "_Read-only projection · auto-regenerated · source of truth is SQLite Graph Memory_\n\n"
    top_content += "## Hierarchy\n\n"
    top_content += "\n".join(hierarchy_links) + "\n"
    
    top_index.write_text(top_content, encoding="utf-8")
    created_wiki_files.append(str(top_index))
    
    return {"status": "success", "wiki_files_count": len(created_wiki_files), "index_file": str(top_index), "files": created_wiki_files}
