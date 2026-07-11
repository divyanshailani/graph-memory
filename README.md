# Graph-Memory

A universal, long-term project memory tool utilizing a local SQLite graph structure to solve context amnesia for AI coding agents.

**Natively built for Antigravity (AG)**, Graph-Memory provides autonomous AI agents with a highly structured, relational brain. It is exposed universally via the **Model Context Protocol (MCP)**, meaning any framework (Claude Desktop, Cursor, Codex, Aider) can share and update the exact same graph in real-time.

## Overview
When AI agents work on complex software projects over long periods, flat markdown files like `project_memory.md` often fail because they lack structural context and the agent forgets the relationships between different files, tasks, and infrastructure.

**Graph-Memory** solves this by providing a **Trust-Weighted Epistemic Graph** database (SQLite-backed) that your agents interact with to store long-term architecture. It forces agents to provide confidence levels on the facts they log, entirely preventing silent hallucinations.

## File Structure

```
Graph memory/
├── .agents/                    # Database and exports (auto-generated per workspace)
│   ├── graph_memory.sqlite     # The isolated SQLite brain
│   └── graph_memory_vis.html   # The interactive visual graph
├── scripts/
│   ├── db.py                   # Core SQLite bindings, schema, and epistemic logic
│   ├── mcp_server.py           # The Universal Model Context Protocol (MCP) Server
│   └── memory_tool.py          # The CLI tool & HTML Visualizer
├── SKILL.md                    # Antigravity native skill instructions and rules
├── README.md                   # This documentation
├── CHANGELOG.md                # Version history
└── ISSUES.md                   # Known bugs and future roadmap
```

## Features
- **Trust-Weighted Epistemic Graph**: The graph strictly tracks *when* a fact was logged, and *how* it was verified. If an agent just assumes a fact, the graph flags it as stale. It only trusts explicit code reads and executed tests.
- **Idempotent Nodes & Edges**: Agents log Tasks, Decisions, Infrastructure, and Bugs as connected nodes.
- **Strict Modeling Rules**: Rules enforced via instructions ensure no orphaned nodes and strict typing.
- **Obsidian-style Vis.js HTML Export**: Generate beautiful, physics-based, dark-mode graph visualizations in your browser. Stale or hallucinated nodes are visually flagged.
- **Universal State**: The database is stored locally in `.agents/graph_memory.sqlite`, meaning Claude Desktop, Cursor, and Antigravity can all read/write to the exact same brain simultaneously.

## Universal Setup (MCP Server)

First, ensure you have the `mcp` SDK installed globally:
```bash
pip install mcp
```

### Claude Desktop Configuration
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

### Cursor / Codex Configuration
Add the server in your MCP settings or `config.toml`:
- **Type**: command
- **Command**: `python3 "/absolute/path/to/Graph memory/scripts/mcp_server.py"`

---

## Pro-Tip: Enabling "Live" Auto-Updates
In Antigravity (AG), Graph-Memory is deeply integrated, meaning the agent automatically updates the database in the background without you asking.

**To get this same "Live Auto-Update" behavior in Claude Desktop, Cursor, or Codex**, you must paste the following rule into your **Project Instructions**, `.cursorrules`, or `.codexrules` file:

```markdown
# Automated Graph Memory Tracking
You have access to a `graph_memory` MCP server. You MUST proactively and automatically use the `add_node` and `add_relation` tools to track project state without the user explicitly asking you to. 

Whenever you:
1. Complete a significant task or milestone.
2. Make an architectural decision.
3. Discover or setup new infrastructure.

Quietly run the graph tools at the end of your turn to log this information so it isn't forgotten.
```
*Without this rule, Claude/Cursor will treat the graph as a purely manual tool and will only update it when explicitly asked.*

---

## Antigravity Installation (Native)
If you are using Antigravity, you can symlink this repository directly into your skills folder to use it natively via CLI:
```bash
ln -s "/path/to/Graph memory" ~/.gemini/config/skills/graph_memory
```

## CLI Usage
If you prefer terminal commands, you can use the script directly. Note that `verification_method` is strictly required:
```bash
# Add a Node
python3 scripts/memory_tool.py add_node "Postgres_DB" "Infrastructure" "source_read" '{"ip": "192.168.1.5"}'

# Add a Relation
python3 scripts/memory_tool.py add_relation "Server_VM" "HAS_DB" "Postgres_DB" "assumed"

# Generate HTML Graph Visualization
python3 scripts/memory_tool.py export_html
```
