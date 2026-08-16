# Epistemic Graph Memory (v3.7.0)

![Epistemic Graph Memory 2D UI Global View](assets/screenshot2.png)

A universal, long-term project memory and structural context tool for AI coding agents (Antigravity, Hermes, Claude, Cursor, Codex, ZCode, Qoder, OpenCode, Ollama).

**Epistemic Graph Memory** provides a local, SQLite-backed knowledge graph with **Dynamic Epistemic Trust Decay**, **First-Class Decision Audit Ledgers**, **Contradiction Detection**, **Codebase AST Call-Graph Awareness** (cross-file), **Automated Lifecycle Hooks**, and **Continuous Micro-Compaction**.

Exposed via the **Model Context Protocol (MCP)** — stdio and **streamable HTTP** — plus a 25-command CLI. Installs itself into 9 agent harnesses with one command.

---

## 🌟 Core Features

### 1. 🪝 Automated Lifecycle Memory (v3.5.0)
* **Harness-Agnostic Hook Dispatcher (`graph-memory hook-event`)**: `PostToolUse` → incremental AST ingest of edited files (<5ms); `Stop` → transcript captured into FTS5 Session_Logs + facts distilled into the graph; `SessionStart` → every installed snapshot file refreshed.
* **9 Framework Integrations**: real event hooks for Claude Code and ZCode; MCP registration + lifecycle protocol for Cursor, Codex, and OpenCode; instruction/snapshot files for Antigravity, Qoder, and Hermes. `graph-memory hook install` — idempotent, non-destructive.

### 2. ⏳ Dynamic Epistemic Trust Decay & Contradiction Detection
* **Cognitive Forgetting Math**: query-time trust decay — `Effective = Base × 0.5^(Δdays/30)` — without mutating baseline data. Re-verification restores 100%.
* **Contradiction Detection (v3.7.0)**: when different agents assert different values for the same fact, the conflict is recorded and surfaced as `⚠ Conflicting Assertions` in snapshots — disagreements become visible instead of silently overwriting.
* **Stale-Node GC (`graph-memory prune`)**: soft-deletes decayed, unreferenced nodes past a staleness threshold.

### 3. 📜 First-Class Multi-Agent Decision Ledger
* **Append-Only Audit Trail**: tracks *which* agent made *what* decision, *why*, and *when* — mechanical AST re-parses are kept out (signal, not noise).
* **Real Reflection Engine (v3.7.0)**: `graph-memory memory reflect` digests the last 30 days of actual decisions into 5 standardized memory categories — real rationales, not templates.

### 4. 🔍 Codebase AST & Cross-File Call Graphs
* **Polyglot AST Ingestion** (`ingest-code`): Python, TypeScript/TSX, JavaScript/JSX, Go, Rust via Tree-sitter — signatures, docstrings, line bounds, snippets.
* **Cross-File Call Resolution (v3.7.0)**: CALLS edges are resolved to definitions across file boundaries (unique-name matching within the project namespace).
* **Batch Ingestion (v3.7.0)**: one connection + one transaction per file — full-repo ingestion is ~17× faster; **hash-skip** makes unchanged re-ingestion near-instant (8.5s → 0.06s on this repo).
* **Trigram Identifier Search (v3.7.0)**: partial identifiers like `effective_tr` match exactly — the default tokenizer can't do that.
* **<5ms Single-File Re-Parsing (`ingest-file`)** with `--root` monorepo-safe namespace pinning.

### 5. 🧠 Hermes-Class Snapshots & Micro-Compaction
* **Prompt-Cache-Stable Snapshots**: deterministic ordering + content fingerprinting — an unchanged graph returns the byte-identical snapshot, keeping agent prompt caches intact.
* **Continuous Micro-Compaction (`distill_session`)**: verbatim user intent preserved; assistant tool output distilled into structured graph facts.
* **Episodic Session Logging & FTS5 Search** (`search-sessions`), auto-populated by lifecycle hooks.

### 6. 🔀 Entity Merging, Hygiene & Visualization
* **Soft-Delete Merging** with canonical pointers and alias tracking; orphan linting; project-root-safe sweeps.
* **2D & GPU-accelerated 3D visualizations** (`export_html`, `export-3d`).

---

## 📦 Installation

```bash
pip install epistemic-graph-memory[all]
```
*Note: The `[all]` extra installs polyglot Tree-sitter AST parser bindings.*

---

## 🔌 MCP Server Configuration

To use Epistemic Graph Memory natively inside Claude Desktop, Cursor, Antigravity, Hermes, or Codex, add the following to your MCP configuration:

```json
{
  "mcpServers": {
    "graph-memory": {
      "command": "graph-memory-mcp"
    }
  }
}
```

### Streamable HTTP Transport (v3.6.0)

For harnesses that only support remote MCP servers (OpenCode) or remotely hosted / Dockerized agents:

```bash
graph-memory-mcp-http                     # http://127.0.0.1:8765/mcp
GRAPH_MEMORY_HTTP_HOST=0.0.0.0 GRAPH_MEMORY_HTTP_PORT=9000 graph-memory-mcp-http
```

Stateless session mode — safe for multiple concurrent agents on one endpoint. Health check at `/health`. Requires the `http` extra (`pip install epistemic-graph-memory[http]`).

---

## 📥 Memory Import & Export (v3.6.0)

Zero-cost migration from the memory formats you already have, and a browsable vault out:

```bash
# Import CLAUDE.md / AGENTS.md / .cursorrules / any markdown memory (sections -> Knowledge_Nodes)
graph-memory import-md CLAUDE.md
graph-memory import-md .cursorrules

# Import a mem0 JSON export (records -> Fact_Nodes)
graph-memory import-mem0 mem0_export.json

# Export curated knowledge as an Obsidian vault with [[wikilinks]] for graph edges
graph-memory export-obsidian ~/vaults/graph-memory
```

---

## 🪝 Framework Auto-Memory Bindings & Lifecycle Hooks (v3.5.0)

One command wires Graph Memory into your agent harness — with **automatic lifecycle capture** where the harness supports event hooks, and an MCP + instruction protocol everywhere else:

```bash
graph-memory hook install                # all frameworks
graph-memory hook install --framework zcode
graph-memory hook status
graph-memory hook refresh                # re-render snapshots now
```

| Framework | Integration | What happens automatically |
| :--- | :--- | :--- |
| **Claude Code** | Event hooks in `~/.claude/settings.json` + auto-context file | PostToolUse → incremental AST ingest of edited files; Stop → transcript distillation into Session_Logs + fact graph; SessionStart → snapshot refresh |
| **ZCode** | Event hooks in `~/.zcode/cli/config.json` (`hooks.enabled: true`) | Same three-event lifecycle via portable `process` hooks |
| **Codex** | Rule file + MCP entry in `~/.codex/config.toml` | Snapshot injection + lifecycle protocol; MCP tools for search/ingest/distill |
| **Cursor** | Rule (`.mdc`) + MCP entry in `~/.cursor/mcp.json` | Snapshot injection + lifecycle protocol via MCP tools |
| **Antigravity** | Skill file (`AUTO_MEMORY.md`) | Snapshot injection + lifecycle protocol |
| **Qoder** | Rule file (`~/.qoder/rules/`) | Snapshot injection + lifecycle protocol |
| **OpenCode** | Marked section in `AGENTS.md` + remote MCP entry in `opencode.json` | Snapshot injection + lifecycle protocol + native MCP tools via `graph-memory-mcp-http` |
| **Hermes** | `MEMORY.md` auto-sync section | Snapshot sync on install/refresh |
| **Claude Desktop** | Env flag on the MCP entry | `GRAPH_MEMORY_AUTO_SNAPSHOT=1` |

The lifecycle is powered by a **harness-agnostic dispatcher** — any harness that can run a shell command on events can use it:

```bash
echo '{"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": "src/main.py"}}' | graph-memory hook-event
```

Events handled: `PostToolUse` (auto-ingest edited file, <5ms), `Stop`/`SessionEnd` (log transcript tail into FTS5 Session_Logs, distill facts, refresh snapshots), `SessionStart` (refresh all installed snapshot files).

---

## 🚀 Quickstart

### 1. Ingest Codebase AST & Build Graph
```bash
# Parse full codebase AST, call graphs, and inheritance
graph-memory ingest-code .

# Incrementally re-parse a single modified file (<5ms)
graph-memory ingest-file graph_memory/core/engine.py --agent Antigravity --rationale "Refactored trust decay"
```

### 2. Generate Active Prompt Snapshot (Hermes Auto-Recall)
```bash
# Output prompt-cache friendly Markdown snapshot for system prompt injection
graph-memory snapshot --max-tokens 600 --min-trust 0.7
```

### 3. Query Decision History & Search
```bash
# Query agent decision audit ledger
graph-memory query-history --agent Hermes --limit 10

# FTS5 search across graph nodes
graph-memory search "effective trust"

# FTS5 search across episodic session logs
graph-memory search-sessions "tree-sitter fallback"
```

### 4. Graph Maintenance & 3D Visualization
```bash
# Lint for orphan nodes and dangling edges
graph-memory lint --fix

# Perform SQLite database vacuum
graph-memory consolidate

# Export WebGL 3D GPU-Accelerated Graph Viewer
graph-memory export-3d memory_3d.html
```

---

## 🛠️ MCP Tool Reference

| MCP Tool | Description |
| :--- | :--- |
| `get_active_snapshot` | Returns prompt-cache friendly Markdown snapshot of active high-trust graph facts. |
| `distill_session` | Performs continuous micro-compaction and fact distillation on session turns. |
| `search_session_history` | Searches historical conversation transcripts using SQLite FTS5. |
| `query_decision_history` | Queries global `Decision_Ledger` by agent, node ID, or timeframe. |
| `read_code_snippet` | Retrieves exact AST signature, docstring, line bounds, and source code snippet. |
| `ingest_file` | Incrementally re-parses a single changed file into the AST graph (<5ms). |
| `merge_entities` | Merges source entity into target entity with canonical pointer redirect. |
| `create_entities` | Creates multiple entities with trust scores and observation payloads. |
| `create_relations` | Creates directional relations between entities with trust metrics. |
| `search_nodes` | FTS5 search across entity names, types, and observation content. |
| `open_nodes` | Serializes subgraphs around specific central nodes. |
| `read_graph` | Serializes complete knowledge graph. |

---

## 💡 Architecture Protocols

### Entity Ontologies
- **`Fact_Node`**: Ground-truth facts derived deterministically from AST, Git, or session distillation.
- **`Knowledge_Node`**: High-level architecture, module summaries, and design decisions.
- **`Episode_Node`**: Workflows, completed task sequences, and milestone records (linked with `FOLLOWED_BY` edges).
- **`Release_Node`**: Formally published software versions and package release records.

---

## 📜 Lineage & Acknowledgments

Graph-Memory was inspired by the [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) and the **Hermes Agent** memory architecture.

* **SQLite WAL & FTS5**: Powered by local SQLite WAL mode for concurrent multi-agent safety and FTS5 for high-speed indexing.
* **Tree-Sitter**: Powered by Tree-sitter for polyglot AST parsing.

---

## 📄 License
MIT License. Created by Divyansh Ailani.
