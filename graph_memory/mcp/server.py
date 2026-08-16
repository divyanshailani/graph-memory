import asyncio
import json
import os
from typing import List, Dict, Any
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from graph_memory.core import engine

# Default DB Path
DB_PATH = engine.get_db_path()

# Ensure DB is initialized
engine.init_db(DB_PATH)

server = Server("graph-memory")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    Exposes the 9 standard Anthropic MCP Memory Tool signatures.
    This makes the package a "Drop-In Replacement" for the official memory server.
    """
    seed_context = engine.get_seed_memory(DB_PATH)
    if os.environ.get("GRAPH_MEMORY_AUTO_SNAPSHOT") == "1":
        from graph_memory.core.snapshot import generate_active_snapshot
        snapshot_str = generate_active_snapshot(DB_PATH, max_tokens=400, min_trust=0.7)
        seed_context = f"{seed_context} | AUTO-SNAPSHOT: {snapshot_str}"
    return [
        types.Tool(
            name="create_entities",
            description="Create multiple new entities in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "The name/ID of the entity"},
                                "entityType": {"type": "string", "description": "The type or label of the entity"},
                                "observations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "An array of observation strings about this entity"
                                }
                            },
                            "required": ["name", "entityType", "observations"]
                        }
                    }
                },
                "required": ["entities"]
            }
        ),
        types.Tool(
            name="create_relations",
            description="Create multiple new relations between entities in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string", "description": "The name of the source entity"},
                                "to": {"type": "string", "description": "The name of the target entity"},
                                "relationType": {"type": "string", "description": "The type of relation"}
                            },
                            "required": ["from", "to", "relationType"]
                        }
                    }
                },
                "required": ["relations"]
            }
        ),
        types.Tool(
            name="add_observations",
            description="Add new observations to existing entities in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "observations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entityName": {"type": "string", "description": "The name of the entity"},
                                "contents": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "An array of observation strings to add"
                                }
                            },
                            "required": ["entityName", "contents"]
                        }
                    }
                },
                "required": ["observations"]
            }
        ),
        types.Tool(
            name="delete_entities",
            description="Delete multiple entities and their associated relations from the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "entityNames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of entity names to delete"
                    }
                },
                "required": ["entityNames"]
            }
        ),
        types.Tool(
            name="delete_observations",
            description="Delete specific observations from entities in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entityName": {"type": "string", "description": "The name of the entity"},
                                "observations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "An array of observation strings to delete"
                                }
                            },
                            "required": ["entityName", "observations"]
                        }
                    }
                },
                "required": ["deletions"]
            }
        ),
        types.Tool(
            name="delete_relations",
            description="Delete multiple relations from the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string", "description": "The name of the source entity"},
                                "to": {"type": "string", "description": "The name of the target entity"},
                                "relationType": {"type": "string", "description": "The type of relation"}
                            },
                            "required": ["from", "to", "relationType"]
                        }
                    }
                },
                "required": ["relations"]
            }
        ),
        types.Tool(
            name="read_graph",
            description=f"Read the entire knowledge graph. [{seed_context}]",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."}
                },
            }
        ),
        types.Tool(
            name="search_nodes",
            description=f"Search for nodes in the knowledge graph based on a query. [{seed_context}]",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "query": {"type": "string", "description": "The search query to match against entity names, types, and observation content."}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="open_nodes",
            description="Open specific nodes in the knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of entity names to retrieve"
                    }
                },
                "required": ["names"]
            }
        ),
        types.Tool(
            name="merge_entities",
            description="Merge a source entity into a target entity, combining observations and updating all associated relations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
                    "sourceName": {"type": "string", "description": "The name of the source entity to merge from (will be soft-deleted)."},
                    "targetName": {"type": "string", "description": "The name of the target entity to merge into (will be preserved)."}
                },
                "required": ["sourceName", "targetName"]
            }
        ),
        types.Tool(
            name="read_code_snippet",
            description="Retrieve the exact source code snippet, signature, docstring, and line bounds for a function or class node.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "node_id": {"type": "string", "description": "The ID of the function or class component node."}
                },
                "required": ["node_id"]
            }
        ),
        types.Tool(
            name="ingest_file",
            description="Incrementally re-parse a single changed file into the AST graph in <5ms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "file_path": {"type": "string", "description": "Absolute or relative path to the modified file on disk."},
                    "agentName": {"type": "string", "description": "Name of the agent triggering the update (e.g. Hermes, Antigravity, Claude)."},
                    "rationale": {"type": "string", "description": "Reason for updating or refactoring this file."},
                    "root": {"type": "string", "description": "Explicit project namespace root (monorepo-safe); must match ingest-code --root for identical node IDs."}
                },
                "required": ["file_path"]
            }
        ),
        types.Tool(
            name="query_decision_history",
            description="Query the global Decision Ledger across all nodes by agent, node ID, or timeframe.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "agentName": {"type": "string", "description": "Filter by agent name (e.g. Hermes, Antigravity, Claude)."},
                    "node_id": {"type": "string", "description": "Filter by specific node ID."},
                    "days": {"type": "integer", "description": "Filter decisions made in the last N days."},
                    "limit": {"type": "integer", "description": "Maximum entries to return (default 50)."}
                }
            }
        ),
        types.Tool(
            name="get_active_snapshot",
            description="Get an ultra-dense, prompt-cache friendly Markdown snapshot of active high-trust memory facts and recent milestones.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "max_tokens": {"type": "integer", "description": "Token limit budget for snapshot (default 600)."},
                    "min_trust": {"type": "number", "description": "Minimum effective trust threshold (default 0.7)."}
                }
            }
        ),
        types.Tool(
            name="distill_session",
            description="Perform continuous micro-compaction and fact distillation on raw session messages while preserving user intent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "session_id": {"type": "string", "description": "Unique session identifier."},
                    "agentName": {"type": "string", "description": "Name of the agent (e.g. Hermes, Antigravity)."},
                    "exchanges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "content": {"type": "string"}
                            },
                            "required": ["role", "content"]
                        }
                    }
                },
                "required": ["session_id", "agentName", "exchanges"]
            }
        ),
        types.Tool(
            name="search_session_history",
            description="Search historical session conversation logs using FTS5 full-text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "query": {"type": "string", "description": "Search query string."},
                    "session_id": {"type": "string", "description": "Optional filter by session ID."},
                    "limit": {"type": "integer", "description": "Maximum logs to return (default 20)."}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="generate_repo_wiki",
            description="Generate hierarchical Markdown Repo Wiki matching Qoder schema.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "target_dir": {"type": "string", "description": "Target output directory (default: .agents/wiki)."},
                    "repo_name": {"type": "string", "description": "Repository name (default: Project)."},
                    "branch": {"type": "string", "description": "Branch name (default: main)."}
                }
            }
        ),
        types.Tool(
            name="get_knowledge_cards",
            description="Extract domain Knowledge Cards across 8 software domains (frontend_style, backend_architecture, build_system, logging_system, configuration_system, dependency_management, error_handling, external_dependency).",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "target_dir": {"type": "string", "description": "Target output directory (default: .agents/wiki)."}
                }
            }
        ),
        types.Tool(
            name="reflect_session_memory",
            description="Reflect session history and decision ledger into persistent memory cards.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to graph_memory.sqlite database."},
                    "target_dir": {"type": "string", "description": "Target output directory (default: .agents)."}
                }
            }
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool executions, mapping Anthropic's standard API to our SQLite backend.
    """
    if not arguments:
        arguments = {}
        
    actual_db_path = arguments.get("db_path") or DB_PATH
    try:
        if name == "create_entities":
            entities = arguments.get("entities", [])
            for ent in entities:
                engine.get_or_create_node(
                    actual_db_path,
                    node_id=ent["name"],
                    label=ent["entityType"],
                    properties={"observations": ent.get("observations", []), "type": ent["entityType"]}
                )
            return [types.TextContent(type="text", text=f"Created {len(entities)} entities successfully.")]

        elif name == "create_relations":
            relations = arguments.get("relations", [])
            for rel in relations:
                engine.create_relation(
                    actual_db_path,
                    source_id=rel["from"],
                    target_id=rel["to"],
                    relation_type=rel["relationType"]
                )
            return [types.TextContent(type="text", text=f"Created {len(relations)} relations successfully.")]

        elif name == "add_observations":
            observations = arguments.get("observations", [])
            for obs in observations:
                for content in obs.get("contents", []):
                    engine.add_observation(actual_db_path, obs["entityName"], content)
            return [types.TextContent(type="text", text=f"Added observations successfully.")]

        elif name == "delete_entities":
            entityNames = arguments.get("entityNames", [])
            for name in entityNames:
                engine.soft_delete_entity(actual_db_path, name)
            return [types.TextContent(type="text", text=f"Soft deleted {len(entityNames)} entities successfully.")]

        elif name == "delete_observations":
            deletions = arguments.get("deletions", [])
            for deletion in deletions:
                node_id = deletion["entityName"]
                obs_to_delete = deletion.get("observations", [])
                
                # Fetch current properties manually to perform deletion
                with engine.get_connection(actual_db_path) as conn:
                    row = conn.execute("SELECT properties FROM Nodes WHERE id = ? AND is_deleted = 0", (node_id,)).fetchone()
                    if row:
                        props = json.loads(row[0]) if row[0] else {}
                        current_obs = props.get("observations", [])
                        new_obs = [o for o in current_obs if o not in obs_to_delete]
                        props["observations"] = new_obs
                        with engine.write_transaction(conn):
                            conn.execute("UPDATE Nodes SET properties = ?, updated_at = ? WHERE id = ?", 
                                         (json.dumps(props), engine.now_iso(), node_id))
                                         
            return [types.TextContent(type="text", text=f"Deleted observations successfully.")]

        elif name == "delete_relations":
            relations = arguments.get("relations", [])
            for rel in relations:
                engine.delete_relation(
                    actual_db_path,
                    source_id=rel["from"],
                    target_id=rel["to"],
                    relation_type=rel["relationType"]
                )
            return [types.TextContent(type="text", text=f"Deleted {len(relations)} relations successfully.")]

        elif name == "read_graph":
            graph = engine.read_graph(actual_db_path)
            return [types.TextContent(type="text", text=json.dumps(graph, indent=2))]

        elif name == "search_nodes":
            query = arguments.get("query", "")
            results = engine.search_nodes(actual_db_path, query)
            return [types.TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "open_nodes":
            names = arguments.get("names", [])
            outputs = []
            for name in names:
                subgraph = engine.serialize_subgraph(actual_db_path, name)
                outputs.append(subgraph)
            return [types.TextContent(type="text", text="\n---\n".join(outputs))]

        elif name == "merge_entities":
            source_name = arguments.get("sourceName", "")
            target_name = arguments.get("targetName", "")
            res = engine.merge_nodes(actual_db_path, source_name, target_name)
            if res.get("status") == "success":
                return [types.TextContent(type="text", text=f"Successfully merged entity '{source_name}' into '{target_name}'.")]
            else:
                return [types.TextContent(type="text", text=f"Error merging entities: {res.get('message')}")]

        elif name == "read_code_snippet":
            node_id = arguments.get("node_id", "")
            subgraph = engine.serialize_subgraph(actual_db_path, node_id)
            return [types.TextContent(type="text", text=subgraph)]

        elif name == "ingest_file":
            file_path = arguments.get("file_path", "")
            agent_name = arguments.get("agentName", "MCP-Agent")
            rationale = arguments.get("rationale", "Incremental file AST ingest")
            root = arguments.get("root")
            from graph_memory.core.ingest import ingest_file
            res = ingest_file(actual_db_path, file_path, agent_name=agent_name, rationale=rationale, root=root)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "query_decision_history":
            agent_name = arguments.get("agentName")
            node_id = arguments.get("node_id")
            days = arguments.get("days")
            limit = arguments.get("limit", 50)
            res = engine.query_decision_ledger(actual_db_path, agent_name=agent_name, node_id=node_id, days=days, limit=limit)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "get_active_snapshot":
            max_tokens = arguments.get("max_tokens", 600)
            min_trust = arguments.get("min_trust", 0.7)
            from graph_memory.core.snapshot import generate_active_snapshot
            snap = generate_active_snapshot(actual_db_path, max_tokens=max_tokens, min_trust=min_trust)
            return [types.TextContent(type="text", text=snap)]

        elif name == "distill_session":
            session_id = arguments.get("session_id", "default_session")
            agent_name = arguments.get("agentName", "Agent")
            exchanges = arguments.get("exchanges", [])
            from graph_memory.core.distill import distill_session_exchanges
            res = distill_session_exchanges(actual_db_path, session_id, agent_name, exchanges)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "search_session_history":
            query = arguments.get("query", "")
            session_id = arguments.get("session_id")
            limit = arguments.get("limit", 20)
            res = engine.search_session_logs(actual_db_path, query, session_id=session_id, limit=limit)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "generate_repo_wiki":
            target_dir = arguments.get("target_dir", ".agents/wiki")
            repo_name = arguments.get("repo_name", "Project")
            branch = arguments.get("branch", "main")
            from graph_memory.core.knowledge import generate_repo_wiki
            res = generate_repo_wiki(actual_db_path, target_dir, repo_name=repo_name, branch=branch)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "get_knowledge_cards":
            target_dir = arguments.get("target_dir", ".agents/wiki")
            from graph_memory.core.knowledge import extract_knowledge_cards
            res = extract_knowledge_cards(actual_db_path, target_dir)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        elif name == "reflect_session_memory":
            target_dir = arguments.get("target_dir", ".agents")
            from graph_memory.core.memory import reflect_session_memory
            res = reflect_session_memory(actual_db_path, target_dir)
            return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error executing {name}: {str(e)}")]

async def run_mcp_server():
    """Runs the MCP server using stdio."""
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            options
        )

def main():
    asyncio.run(run_mcp_server())

if __name__ == "__main__":
    main()
