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
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
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
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
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
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
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
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
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
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."},
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
            description="Read the entire knowledge graph.",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Optional path to a specific graph_memory.sqlite database for cross-project queries."}
                },
            }
        ),
        types.Tool(
            name="search_nodes",
            description="Search for nodes in the knowledge graph based on a query.",
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
