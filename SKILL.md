---
name: graph-memory
description: Long-term project memory utilizing a local SQLite graph structure to solve context amnesia. Provides commands to add nodes, relationships, and query state.
---

# Graph Memory

You have access to a "Graph Memory" system for storing long-term project context, state, infrastructure details, and decisions.

**CRITICAL: Stop using flat markdown files like `agents.md` or `project_memory.md` for tracking project state. They cause context amnesia over long periods.**

Instead, use the `memory_tool.py` script provided in this skill's `scripts/` directory to manage a local SQLite database that acts as a graph.

The database is automatically isolated per-project. It is stored at `.agents/graph_memory.sqlite` in the current workspace.

## Available Commands

You can run the script using your terminal tool:
`python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py <command> [args...]`

### 1. Adding Data
- **Add a Node:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_node <id> <type> <verification_method> [attributes_json]`
  *Example:* `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_node "Postgres_DB" "Infrastructure" "source_read" '{"ip": "192.168.1.5", "port": 5432}'`
  *Example:* `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_node "Bug_Fix_12" "Task" "test_executed" '{"status": "completed", "date": "2023-10-27"}'`

- **Add a Relationship:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_relation <source_id> <relation_type> <target_id> <verification_method> [attributes_json]`
  *Example:* `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_relation "Server_VM" "HAS_DB" "Postgres_DB" "source_read"`
  *Example:* `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py add_relation "Bug_Fix_12" "AFFECTS" "Auth_Service" "assumed"`

### 2. Querying Data
- **Get Node:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py get_node <id>`
  Returns the node and all its incoming/outgoing relationships.
- **Search by Type:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py search_nodes <type>`
  Returns all nodes of a specific type (e.g., "Infrastructure", "Task").

### 3. Visualizing (For the User)
If the user wants to see the graph, you can generate visualizations:
- **Export HTML:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py export_html`
  Generates an interactive HTML graph at `.agents/graph_memory_vis.html`.
- **Export Obsidian:** `python3 ~/.gemini/config/skills/graph_memory/scripts/memory_tool.py export_obsidian <target_dir>`
  Exports the graph as interconnected Markdown files for use in Obsidian.

## When to use Graph Memory
1. **Upon completing a task:** Log the task as a node, and relate it to the files/services it modified.
2. **When discovering infrastructure:** Log IPs, ports, and architectural decisions.
3. **When starting a new sub-task:** Query the graph for relevant services to recall past context without asking the user.

## Best Practices for Graph Modeling (Robustness)
To prevent the graph from becoming cluttered, disjointed, or confusing over time, you MUST follow these logical rules when adding to the memory:

1. **The "No Orphans" Rule:** EVERY time you create a new node (`add_node`), you MUST immediately run `add_relation` to connect it to an existing node in the graph. Do not leave nodes floating!
2. **Tie to the Root:** If a new node doesn't clearly connect to a specific component, tie it to the main project node (e.g., `add_relation "New_Task" "PART_OF" "Project_Name"`).
3. **Standardized Node Types:** Stick to a consistent set of node types: `Project`, `Architecture`, `Infrastructure`, `Task`, `Decision`, `Bug`, `Feature`.
4. **Standardized Relationship Verbs:** Use clear, uppercase verbs for relations: `IMPLEMENTS`, `DEPENDS_ON`, `FIXES`, `PART_OF`, `COMMUNICATES_WITH`, `USES`, `EXTENDS`.
5. **Idempotency & Deduplication:** Before adding a generic node like "Frontend", check if a node like "Vercel_Frontend" already exists to avoid creating duplicates. Use specific IDs (e.g., `Azure_PostgreSQL` rather than just `Database`).
6. **Strict Verification Enums:** You MUST provide a valid `verification_method` when logging data. Use strong methods (`source_read`, `test_executed`, `endpoint_tested`) when you have actual evidence. If you just assume something or haven't verified it, you MUST use `agent_self_report` or `assumed`. Using weak methods will visually flag the node as untrusted to humans and other agents, preventing confident hallucinations.
