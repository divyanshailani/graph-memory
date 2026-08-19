<p align="center">
  <img src="assets/screenshot2.png" width="720" alt="2D graph visualization of a Python codebase">
</p>

<h1 align="center">Epistemic Graph Memory</h1>

<p align="center">
  A local knowledge graph that gives AI coding agents long-term project memory.<br>
  5,000 lines of Python. Zero cloud dependencies. One <code>pip install</code>.
</p>

<p align="center">
  <code>python -m pip install 'epistemic-graph-memory[all]'</code>
</p>

<p align="center">
  <a href="https://pypi.org/project/epistemic-graph-memory/"><img src="https://img.shields.io/pypi/v/epistemic-graph-memory?color=blue" alt="PyPI"></a>
  <a href="https://github.com/divyanshailani/graph-memory/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <img src="https://img.shields.io/badge/tests-57%20passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python">
</p>

---

### The problem

AI coding agents reconstruct project context from scratch every session. They re-read files they've already read, re-derive architecture they've already derived, and lose decisions made yesterday. Claude Code, Cursor, Codex, OpenCode — they all forget.

### The solution

A **SQLite-backed knowledge graph** that lives in your project at `.agents/graph_memory.sqlite`. It ingests your codebase's AST (functions, classes, call graphs, imports), records agent decisions in an append-only ledger, detects when agents contradict each other, and produces deterministic snapshots that inject directly into agent system prompts — with byte-stable caching so prompt caches stay hot.

All 19 MCP tools, a 28-command CLI, lifecycle hooks for 9 agent harnesses, and a streamable HTTP endpoint for remote agents.

---

## What it actually does

**Code understanding.** Parses Python, TypeScript, JS/JSX, Go, and Rust via Tree-sitter. Extracts signatures, docstrings, line ranges, call graphs, and inheritance. Cross-file call resolution wires stubs to real definitions across your entire repo. Batch ingestion processes this repo's 37 files in 0.45 seconds; unchanged re-ingests take 0.06 seconds (hash-skip).

**Agent memory.** Every decision an agent makes — what it changed, why, when — goes into an append-only `Decision_Ledger`. A reflection engine digests the last 30 days of real decisions into structured memory cards. When two agents disagree about a fact (different values for the same field), the contradiction is recorded and surfaced — no silent overwrites.

**Trust decay.** Facts decay over time with `effective = base × 0.5^(days/30)`. Re-verifying a fact resets it to 100%. Stale, unreferenced nodes get garbage-collected. This means the graph self-maintains — old assumptions fade, recent verifications stay sharp.

**Prompt injection.** `graph-memory snapshot` produces a deterministic, content-fingerprinted Markdown snapshot. If nothing changed, you get the exact same bytes — so Claude's prompt cache, Cursor's context cache, whatever — stays warm. Zero wasted tokens on unchanged context.

**Transport.** Runs over stdio MCP (Claude Desktop, Cursor, Codex) and streamable HTTP MCP (OpenCode, Docker, remote agents). One binary, both transports. Health check at `/health`.

**Import / export.** Migrating from mem0? `graph-memory import-mem0 export.json`. Have a CLAUDE.md? `graph-memory import-md CLAUDE.md`. Want a browsable Obsidian vault with `[[wikilinks]]` for every graph edge? `graph-memory export-obsidian ~/vault`.

---

## Setup

```bash
python -m pip install 'epistemic-graph-memory[all]'
```

The `[all]` extra installs Tree-sitter parsers for all 7 language variants plus the HTTP transport (uvicorn + starlette). If you only need Python:

```bash
python -m pip install epistemic-graph-memory
```

### MCP configuration

Add to your agent's MCP config:

```json
{
  "mcpServers": {
    "graph-memory": {
      "command": "graph-memory-mcp"
    }
  }
}
```

For remote-only agents (OpenCode, Docker):

```bash
graph-memory-mcp-http                    # http://127.0.0.1:8765/mcp
```

Then point your agent at `http://127.0.0.1:8765/mcp`.

**Security (v3.8.0):** The HTTP server defaults to localhost (127.0.0.1) and includes DNS rebinding protection. For remote deployment:

- Set `GRAPH_MEMORY_API_KEY` environment variable to require authentication
- Use a reverse proxy (nginx, Caddy) with TLS
- Bind to `0.0.0.0` only behind a firewall/VPN
- Never expose the server directly to the public internet (it provides full filesystem and database access)

```bash
GRAPH_MEMORY_API_KEY=your-secret-key graph-memory-mcp-http
```

### One-command agent hooks

```bash
graph-memory hook install                 # auto-detect and configure all frameworks
graph-memory hook install --framework cursor
graph-memory hook status
```

This wires lifecycle capture into Claude Code, ZCode, Cursor, Codex, OpenCode, Antigravity, Qoder, and Hermes — PostToolUse triggers incremental AST ingest of edited files (<5ms), session-end distills transcripts into graph facts, and session-start refreshes all snapshots.

---

## CLI

```bash
# Ingest entire codebase (polyglot AST + call graphs)
graph-memory ingest-code .

# Re-parse a single changed file (<5ms, skips if unchanged)
graph-memory ingest-file src/engine.py

# Generate prompt-cache-stable snapshot
graph-memory snapshot --max-tokens 600 --min-trust 0.7

# Search nodes (FTS5 + identifier substring fallback)
graph-memory search "effective_tr"
graph-memory search "trust decay"

# Decision audit trail
graph-memory query-history --agent Hermes --days 7

# Contradiction detection
graph-memory contradictions

# Stale-node garbage collection
graph-memory prune --days 60

# Import existing memories
graph-memory import-md CLAUDE.md
graph-memory import-mem0 memories.json

# Export to Obsidian vault
graph-memory export-obsidian ~/vaults/my-project

# HTML / 3D visualization
graph-memory export-html graph.html
graph-memory export-3d graph_3d.html
```

---

## MCP tools

| Tool | What it does |
|---|---|
| `get_active_snapshot` | Deterministic, cache-stable Markdown snapshot of high-trust graph state |
| `distill_session` | Micro-compaction: distills raw transcript turns into structured graph facts |
| `search_session_history` | FTS5 search across episodic session logs |
| `query_decision_history` | Append-only decision ledger (who changed what, why, when) |
| `search_nodes` | FTS5 + substring search across nodes |
| `read_code_snippet` | AST-derived signature, docstring, line bounds, source snippet |
| `ingest_file` | Incremental single-file AST re-parse (<5ms, hash-skip) |
| `create_entities` | Create graph nodes with trust scores |
| `create_relations` | Create directed edges between nodes |
| `merge_entities` | Merge entities with canonical pointer redirect |
| `open_nodes` | Serialize subgraphs around specific nodes |
| `read_graph` | Serialize the complete knowledge graph |

---

## Architecture

```
graph_memory/
├── core/
│   ├── engine.py        # SQLite graph engine: CRUD, trust decay, ledger, search, batch upsert, contradictions, prune
│   ├── ingest.py        # Tree-sitter AST ingestion, batch pipeline, cross-file call resolution
│   ├── importers.py     # Markdown + mem0 import
│   ├── obsidian.py      # Obsidian vault export with [[wikilinks]]
│   ├── snapshot.py      # Deterministic, cache-stable snapshot generation
│   ├── memory.py        # Data-driven reflection engine
│   ├── lifecycle.py      # Harness-agnostic event dispatcher
│   ├── distill.py       # Session transcript micro-compaction
│   └── knowledge.py     # LLM-powered MOC summarization
├── mcp/
│   ├── server.py        # Stdio MCP server (19 tools)
│   └── http_server.py   # Streamable HTTP MCP transport
├── integrations/
│   └── framework_hooks.py  # 9-framework auto-install + lifecycle wiring
└── cli.py               # 28-command CLI
```

**Storage**: Single SQLite file per project at `.agents/graph_memory.sqlite`. WAL mode for concurrent safety. FTS5 for full-text search. No external databases, no servers, no cloud.

**Node types**: `Fact_Node` (deterministic ground truth from AST/Git), `Knowledge_Node` (architecture, design decisions), `Episode_Node` (completed task sequences), `Release_Node` (published versions).

**Trust model**: Query-time decay — `effective = base × 0.5^(Δdays/half_life)`. Re-verification resets to 100%. Stale, unreferenced nodes get soft-deleted by the prune command.

---

## Numbers

| Metric | Value |
|---|---|
| Source code | 5,069 lines Python |
| Test code | 1,672 lines, 57 tests |
| MCP tools | 19 |
| CLI commands | 28 |
| Agent harnesses | 9 |
| AST languages | 7 variants (Python, TS, TSX, JS, JSX, Go, Rust) |
| Dependencies | 4 runtime (mcp, tree-sitter + 2 parsers) |
| External services | 0 |

---

## License

MIT — [Divyansh Ailani](https://github.com/divyanshailani)
