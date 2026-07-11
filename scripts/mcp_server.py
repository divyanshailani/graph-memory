import sys
import json
import os
from mcp.server.fastmcp import FastMCP
from db import init_db, add_node as db_add_node, add_relation as db_add_relation, get_node as db_get_node, get_all_nodes, get_all_relations

# Initialize FastMCP Server
mcp = FastMCP("Graph Memory Server")

def _set_workspace(workspace_dir: str):
    """Helper to set the workspace environment variable so db.py knows where to save."""
    os.environ["GRAPH_MEMORY_WORKSPACE"] = workspace_dir
    init_db()

@mcp.tool()
def add_node(workspace_dir: str, id: str, type: str, verification_method: str, attributes: str = "{}") -> str:
    """
    Adds a new node to the project's graph memory.
    
    Args:
        workspace_dir: The absolute path to the user's current project workspace.
        id: Unique identifier for the node (e.g. "Postgres_DB", "Task_123")
        type: The category of the node (e.g. "Project", "Architecture", "Infrastructure", "Task", "Decision", "Bug", "Feature")
        verification_method: REQUIRED enum determining trust level. Must be one of: 'source_read', 'test_executed', 'endpoint_tested', 'agent_self_report', 'assumed'. Only the first 3 will refresh the node's staleness timer.
        attributes: A JSON string containing key-value metadata (default: "{}")
    """
    _set_workspace(workspace_dir)
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError:
        return "Error: attributes must be a valid JSON string."
        
    try:
        db_add_node(id, type, verification_method, attrs)
        return f"Successfully added node: {id} (Type: {type}, Verification: {verification_method}) to workspace {workspace_dir}"
    except Exception as e:
        return f"Error adding node: {str(e)}"

@mcp.tool()
def add_relation(workspace_dir: str, source: str, relation: str, target: str, verification_method: str, attributes: str = "{}") -> str:
    """
    Adds a relationship between two existing nodes in the graph memory.
    
    Args:
        workspace_dir: The absolute path to the user's current project workspace.
        source: The ID of the source node
        relation: The relationship verb (e.g. "IMPLEMENTS", "DEPENDS_ON", "FIXES", "PART_OF", "USES")
        target: The ID of the target node
        verification_method: REQUIRED enum determining trust level. Must be one of: 'source_read', 'test_executed', 'endpoint_tested', 'agent_self_report', 'assumed'.
        attributes: A JSON string containing key-value metadata (default: "{}")
    """
    _set_workspace(workspace_dir)
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError:
        return "Error: attributes must be a valid JSON string."
        
    try:
        db_add_relation(source, relation, target, verification_method, attrs)
        return f"Successfully added relation: {source} -[{relation}]-> {target} (Verification: {verification_method}) in workspace {workspace_dir}"
    except Exception as e:
        return f"Error adding relation: {str(e)}"

@mcp.tool()
def get_node(workspace_dir: str, id: str) -> str:
    """
    Retrieves a node and all of its incoming and outgoing relationships.
    Useful for recalling context about a specific architectural piece or task.
    
    Args:
        workspace_dir: The absolute path to the user's current project workspace.
        id: The unique identifier of the node to retrieve
    """
    _set_workspace(workspace_dir)
    data = db_get_node(id)
    if not data:
        return f"Node '{id}' not found in memory."
    return json.dumps(data, indent=2)

@mcp.tool()
def refresh_graph_visualization(workspace_dir: str) -> str:
    """
    Generates the interactive HTML visualization of the graph memory and saves it to .agents/graph_memory_vis.html.
    Use this when the user asks to "see", "view", or "visualize" the graph.
    
    Args:
        workspace_dir: The absolute path to the user's current project workspace.
    """
    _set_workspace(workspace_dir)
    import subprocess
    try:
        # Get absolute path to memory_tool.py relative to this file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        memory_tool_path = os.path.join(script_dir, 'memory_tool.py')
        
        # We need to run it with the CWD set to workspace_dir so memory_tool.py picks it up correctly
        result = subprocess.run(
            [sys.executable, memory_tool_path, 'export_html'], 
            cwd=workspace_dir,
            env=os.environ,
            capture_output=True, 
            text=True,
            check=True
        )
        return f"Graph visualization generated successfully at {workspace_dir}/.agents/graph_memory_vis.html."
    except Exception as e:
        return f"Failed to generate visualization: {str(e)}"

if __name__ == "__main__":
    mcp.run()
