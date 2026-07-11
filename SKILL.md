---
name: graph-memory
description: Long-term project memory utilizing a local SQLite graph structure to solve context amnesia. Provides commands to add nodes, relationships, and query state natively.
---

# Graph Memory (Trust-Weighted)

You have access to a "Graph Memory" system for storing long-term project context, state, infrastructure details, and decisions.

**CRITICAL: Stop using flat markdown files like `agents.md` or `project_memory.md` for tracking project state. They cause context amnesia over long periods.**

Instead, use the `graph-memory` global CLI tool to manage a local SQLite database that acts as a trust-weighted epistemic graph. 

The database is automatically isolated per-project. It is stored at `.agents/graph_memory.sqlite` in the current workspace.

## Available Commands

You must run the `graph-memory` CLI in your terminal:

### 1. Adding Data (Always provide a Trust Score!)
You **must** use the `--trust` flag.
- **1.0**: Verified hard facts (e.g., successful terminal exits, explicit human confirmation)
- **0.6 - 0.8**: Assumptions, unverified plans, or self-reported agent claims.

- **Add a Node (Atomic Linking):** `graph-memory add_node <id> <type> [attributes_json] --trust <score> --link-to <parent_id> --link-type <relation>`
  *Example:* `graph-memory add_node "Postgres_DB" "Infrastructure" '{"ip": "192.168.1.5"}' --trust 1.0 --link-to "Project_Graph_Memory" --link-type "PART_OF"`
  *Tip:* ALWAYS use `--link-to` to atomically link a new node to the graph in one command, saving tokens!

- **Add a Relationship:** `graph-memory add_relation <source_id> <relation_type> <target_id> [attributes_json] --trust <score>`
  *Example:* `graph-memory add_relation "Server_VM" "HAS_DB" "Postgres_DB" '{"verified": true}' --trust 1.0`

### 2. Querying Data
- **Get Node & Subgraph:** `graph-memory get_node <id> --min-trust <score>`
  Returns the node and its immediate neighborhood. It automatically filters out low-trust hallucinations.
  *Example:* `graph-memory get_node "Postgres_DB" --min-trust 0.6`

- **Semantic Search:** `graph-memory search <query> --min-trust <score>`
  Full-Text Search across the graph to recall context.
  *Example:* `graph-memory search "database credentials" --min-trust 0.6`

### 3. Brownfield Project Ingestion (Skeleton-to-Meat)
When dropped into a massive existing project, DO NOT attempt to read 10,000 files manually. Use the built-in ingestion engine!
- **Ingest AST Skeleton:** `graph-memory ingest-code .`
  Recursively crawls the codebase using Tree-sitter and maps out all Folders, Files, Classes, Functions, and Imports into structural `MOC_Hub` nodes.
- **Auto-Summarize MOCs:** `graph-memory summarize-mocs`
  Requires `GEMINI_API_KEY`. Queries the LLM to write expert-level business logic summaries for all `MOC_Hub` clusters and saves them back into the graph.

### 4. Visualizing (For the User)
If the user wants to see the graph, generate a visualization:
- **Export HTML:** `graph-memory export_html .agents/graph_memory_vis.html`

## When to use Graph Memory
1. **Upon completing a task:** Log the task as a node, and relate it to the files/services it modified.
2. **When discovering infrastructure:** Log IPs, ports, and architectural decisions.
3. **When starting a new sub-task:** Query the graph for relevant services to recall past context without asking the user.

## Best Practices for Graph Modeling (Robustness)
To prevent the graph from becoming cluttered, disjointed, or confusing over time, you MUST follow these logical rules:

1. **The "No Orphans" Rule:** EVERY time you create a new node, you MUST connect it to the graph using the `--link-to` flag on `add_node`. Do not leave nodes floating!
   - *Garbage Collection:* You should periodically run `graph-memory sweep --root <Main_Project_Node>` to automatically find and soft-delete any accidentally orphaned nodes to keep your context pristine.
2. **Tie to the Root:** If a new node doesn't clearly connect to a specific component, tie it to the main project node using `--link-to`.
3. **Standardized Node Types:** Stick to a consistent set of node types: `Project`, `Architecture`, `Infrastructure`, `Task`, `Decision`, `Bug`, `Feature`.
4. **Standardized Relationship Verbs:** Use clear, uppercase verbs for relations: `IMPLEMENTS`, `DEPENDS_ON`, `FIXES`, `PART_OF`, `COMMUNICATES_WITH`, `USES`, `EXTENDS`.
5. **Idempotency & Deduplication:** Check if an entity exists before creating duplicates.
6. **Active Filtering:** Always use `--min-trust 0.6` (or higher) when searching to explicitly prevent your own context window from being poisoned by deprecated or hallucinated AI data.
