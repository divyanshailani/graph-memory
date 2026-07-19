# Epistemic Graph Memory

![Epistemic Graph Memory 2D UI Global View](assets/screenshot2.png)

A local SQLite graph database designed to track long-term state and structural context for AI coding agents.

Exposed via the **Model Context Protocol (MCP)**, allowing agents (Claude Desktop, Cursor, Codex, OpenHands, Local Ollama agents, etc.) to query and update project blueprints synchronously.

## Features
- **AST Parsing (`ingest-code`)**: Uses Tree-sitter to map local codebases into a node-edge graph hierarchy. Supports Python, TypeScript, JavaScript, Go, and Rust.
- **REST Summary Pipeline (`summarize-mocs`)**: Auto-generates high-level module summaries via LLM APIs.
- **Trust-Weighted Graph**: Employs trust scoring (`--trust`) to segment deterministic facts from AI-generated assumptions.
- **Visualizations**: Generates local HTML exports for inspecting graph state.
- **SQLite FTS5**: Backed by a standard `.agents/graph_memory.sqlite` file using FTS5 for query execution.

## Installation

```bash
pip install epistemic-graph-memory[all]
```
*Note: The `[all]` extra installs polyglot Tree-sitter AST bindings.*

## MCP Server Configuration

Standard MCP integration. Add the following to your AI framework's configuration:

```json
{
  "mcpServers": {
    "graph-memory": {
      "command": "graph-memory-mcp"
    }
  }
}
```

## Quickstart

Initialize a codebase:

```bash
# 1. Map repository AST
graph-memory ingest-code ./src

# 2. Generate module summaries (Requires GEMINI_API_KEY)
export GEMINI_API_KEY="your_api_key_here"
graph-memory summarize-mocs
```

## CLI Reference

The `graph-memory` CLI accesses the local database at `.agents/graph_memory.sqlite`.

```bash
# Ingest Code & Auto-Summarize
graph-memory ingest-code .
graph-memory summarize-mocs

# Add Entity / Relation
graph-memory add_node "Postgres_DB" "Database" '{"observations": ["Found in docker-compose."]}'
graph-memory add_relation "Server_VM" "HAS_DB" "Postgres_DB"

# Query
graph-memory get_node "Postgres_DB"
graph-memory search "Assumed based on backend"

# Maintenance & Export
graph-memory sweep
graph-memory export_html my_graph.html
```

To override the default database location:
```bash
export GRAPH_MEMORY_DB_PATH="/path/to/database.sqlite"
```

## Advanced Schema (Agent Protocols)

Graph-Memory's `--trust` flag is augmented by enforcing a strict JSON metadata schema within the `[attributes_json]` field. When autonomous agents (Claude, Codex, Antigravity) log nodes and relations, they must standardize three core paradigms:

1. **Multi-Agent Provenance & Tool Sourcing:**
   Record *who* created the knowledge and *where* it came from.
   ```json
   {"created_by": "Claude", "source": "AST", "verified_by": "Human"}
   ```

2. **Expanded Trust Protocol:**
   Rather than just passing a flat `--trust` float, agents inject deeper confidence metrics.
   ```json
   {"confidence": 0.8, "verification_source": "pytest", "last_verified": "2026-07-20"}
   ```

3. **Node Distinctions & Execution Workflows:**
   Nodes must adhere to strict type ontologies to separate deterministic structure from history:
   - `Fact_Node`: Deterministic ground-truth (AST, Git, filesystem).
   - `Knowledge_Node`: Architecture, Design decisions, LLM summaries.
   - `Episode_Node`: Execution workflows, completed task sequences ("How was this bug fixed?"). Agents link `Episode_Node` steps using `FOLLOWED_BY` edges.

## Inspiration & Lineage

Graph-Memory was heavily inspired by the [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). 

**What we adopted from OKF:**
- The philosophy of a universal, vendor-neutral knowledge format for AI agents.
- The emphasis on explicit, graph-shaped relationships between concepts (rather than flat text).

**Where we diverged:**
- **Storage:** Instead of static Markdown files (which agents struggle to mutate safely), we use a true local SQLite graph database with FTS5 indexing.
- **Ingestion:** Instead of blind LLM extraction, we use deterministic AST parsing (Tree-sitter) to mathematically guarantee code structural accuracy.
- **Verification:** We implement explicit `--trust` scoring in the SQL schema to isolate and quarantine AI hallucinations.
