---
name: graph-memory
description: Local SQLite graph structure for project state tracking. Provides commands to manage nodes and relationships natively.
---

# Graph Memory (Trust-Weighted)

A local SQLite graph database for tracking project context, architecture, and state. 
Isolated per-project at `.agents/graph_memory.sqlite`. Do not use flat markdown files for tracking state.

## CLI Usage (`graph-memory`)

### 1. Data Modification (Requires `--trust` flag)
Trust scores:
- **1.0**: Verified hard facts (terminal exits, explicit human confirmation).
- **0.6 - 0.8**: Assumptions, unverified plans, AI claims.

**Add Node:**
`graph-memory add_node <id> <type> [attributes_json] --trust <score> --method <human|llm> --link-to <parent_id> --link-type <relation>`
*Example:* `graph-memory add_node "Postgres_DB" "Fact_Node" '{"ip": "192.168.1.5", "created_by": "Antigravity", "source": "AST", "confidence": 1.0}' --trust 1.0 --method human --link-to "Project_Graph_Memory" --link-type "PART_OF"`

**Add Relationship:**
`graph-memory add_relation <source_id> <relation_type> <target_id> [attributes_json] --trust <score> --method <human|llm>`
*Example:* `graph-memory add_relation "Server_VM" "HAS_DB" "Postgres_DB" '{"verified_by": "pytest", "confidence": 0.9}' --trust 1.0 --method human`

### 2. Querying
**Get Node Neighborhood:**
`graph-memory get_node <id> --min-trust <score>`

**Full-Text Search:**
`graph-memory search <query> --min-trust <score>`

### 3. AST Ingestion
**Parse Codebase AST:**
`graph-memory ingest-code .`
Generates structural AST nodes for the current directory.

**Generate Summaries (Requires `GEMINI_API_KEY`):**
`graph-memory summarize-mocs`
Uses LLM to summarize ingested structural hubs.

### 4. Visualization
**HTML Export:**
`graph-memory export_html .agents/graph_memory_vis.html`

**3D Interactive Export:**
`graph-memory export-3d .agents/graph_3d.html`

## Graph Modeling Best Practices
1. **Link New Nodes:** Always use `--link-to` when calling `add_node` to prevent orphaned nodes.
2. **Standard Types (Strict Ontology):** 
   - `Fact_Node`: Deterministic ground-truth (AST, Git, filesystem).
   - `Knowledge_Node`: Architecture, Design decisions, LLM summaries.
   - `Episode_Node`: Completed execution workflows/tasks.
3. **Advanced Protocol (JSON):** Always inject `created_by`, `source`, `confidence`, and `verification_source` into `[attributes_json]`.
4. **Standard Relations:** `IMPLEMENTS`, `DEPENDS_ON`, `FIXES`, `PART_OF`, `FOLLOWED_BY` (for Episodes).
4. **Deduplication:** Check node existence before creation.
5. **Garbage Collection:** Run `graph-memory sweep --root <Main_Project_Node>` to remove orphaned nodes.
6. **Active Filtering:** Query with `--min-trust 0.6` to exclude low-trust data.
