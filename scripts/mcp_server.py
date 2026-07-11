import sys
import json
import os
from mcp.server.fastmcp import FastMCP
from db import init_db, add_node as db_add_node, add_relation as db_add_relation, get_node as db_get_node, get_all_nodes, get_all_relations

# Initialize FastMCP Server
mcp = FastMCP("Graph Memory Server")

@mcp.tool()
def add_node(id: str, type: str, attributes: str = "{}") -> str:
    """
    Adds a new node to the project's graph memory.
    
    Args:
        id: Unique identifier for the node (e.g. "Postgres_DB", "Task_123")
        type: The category of the node (e.g. "Project", "Architecture", "Infrastructure", "Task", "Decision", "Bug", "Feature")
        attributes: A JSON string containing key-value metadata (default: "{}")
    """
    init_db()
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError:
        return "Error: attributes must be a valid JSON string."
        
    db_add_node(id, type, attrs)
    return f"Successfully added node: {id} (Type: {type})"

@mcp.tool()
def add_relation(source: str, relation: str, target: str, attributes: str = "{}") -> str:
    """
    Adds a relationship between two existing nodes in the graph memory.
    
    Args:
        source: The ID of the source node
        relation: The relationship verb (e.g. "IMPLEMENTS", "DEPENDS_ON", "FIXES", "PART_OF", "USES")
        target: The ID of the target node
        attributes: A JSON string containing key-value metadata (default: "{}")
    """
    init_db()
    try:
        attrs = json.loads(attributes)
    except json.JSONDecodeError:
        return "Error: attributes must be a valid JSON string."
        
    db_add_relation(source, relation, target, attrs)
    return f"Successfully added relation: {source} -[{relation}]-> {target}"

@mcp.tool()
def get_node(id: str) -> str:
    """
    Retrieves a node and all of its incoming and outgoing relationships.
    Useful for recalling context about a specific architectural piece or task.
    
    Args:
        id: The unique identifier of the node to retrieve
    """
    init_db()
    data = db_get_node(id)
    if not data:
        return f"Node '{id}' not found in memory."
    return json.dumps(data, indent=2)

@mcp.tool()
def refresh_graph_visualization() -> str:
    """
    Generates the interactive HTML visualization of the graph memory and saves it to .agents/graph_memory_vis.html.
    Use this when the user asks to "see", "view", or "visualize" the graph.
    """
    # Simply call the existing CLI script to generate the HTML
    import subprocess
    try:
        # Get absolute path to memory_tool.py relative to this file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        memory_tool_path = os.path.join(script_dir, 'memory_tool.py')
        
        result = subprocess.run(
            [sys.executable, memory_tool_path, 'export_html'], 
            capture_output=True, 
            text=True,
            check=True
        )
        return "Graph visualization generated successfully at .agents/graph_memory_vis.html. Tell the user to open this file in their browser."
    except Exception as e:
        return f"Failed to generate visualization: {str(e)}"

if __name__ == "__main__":
    init_db()
    mcp.run()
