# Graph Memory for Antigravity

A long-term project memory skill utilizing a local SQLite graph structure to solve context amnesia for AI coding agents.

## Overview
When AI agents work on complex software projects over long periods (weeks or months), flat markdown files like `project_memory.md` often fail because they lack structural context, become too long to read, or the agent forgets the relationships between different files, tasks, and infrastructure.

**Graph Memory** solves this by providing a relational graph database (SQLite-backed) that the agent interacts with directly via CLI.

## Features
- **Idempotent Nodes & Edges**: Agents can log Tasks, Decisions, Infrastructure, and Bugs.
- **Strict Modeling Rules**: Rules enforced via `SKILL.md` ensure no orphaned nodes and strict typing.
- **Obsidian-style Vis.js HTML Export**: Run a simple command to output a beautiful, physics-based, dark-mode graph visualization in your browser.
- **Obsidian Markdown Export**: Export the graph directly into Obsidian-compatible markdown files with bidirectional links.

## Installation
If you are using Antigravity, you can symlink this repository directly into your skills folder:
```bash
ln -s "/path/to/Graph memory" ~/.gemini/config/skills/graph_memory
```

## CLI Usage
The skill interacts via a python script:
```bash
# Add a Node
python3 scripts/memory_tool.py add_node "Postgres_DB" "Infrastructure" '{"ip": "192.168.1.5"}'

# Add a Relation
python3 scripts/memory_tool.py add_relation "Server_VM" "HAS_DB" "Postgres_DB"

# Generate HTML Graph Visualization
python3 scripts/memory_tool.py export_html
```

## Universal Setup (MCP Server)
Graph Memory comes with a Model Context Protocol (MCP) server so it can be universally accessed by any AI coding framework (Claude Desktop, Cursor, Aider, etc.). Since all frameworks store data in `.agents/graph_memory.sqlite` relative to the workspace, they all share the exact same brain!

First, ensure you have the `mcp` SDK installed globally:
```bash
pip install mcp
```

### Claude Desktop
Add the following to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "graph_memory": {
      "command": "python3",
      "args": ["/absolute/path/to/Graph memory/scripts/mcp_server.py"]
    }
  }
}
```

### Cursor / Codeium
Add the server in your MCP settings:
- **Type**: command
- **Command**: `python3 "/absolute/path/to/Graph memory/scripts/mcp_server.py"`


## Data Storage
The SQLite database and exported HTML files are stored safely out of version control in the `.agents/` directory of the workspace where the agent is running.
