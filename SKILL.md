---
name: graph-memory
description: Local SQLite knowledge graph for AI agent project memory. Ingests codebase AST, tracks agent decisions, detects contradictions, and produces cache-stable prompt snapshots. Install via pip, use via CLI or MCP.
---

# Graph Memory

A local SQLite knowledge graph at `.agents/graph_memory.sqlite` that gives AI coding agents long-term project memory. Ingests codebase AST (Python, TypeScript, Go, Rust via Tree-sitter), tracks agent decisions in an append-only ledger, detects contradictions between agents, and produces prompt-cache-stable snapshots.

## Installation

```bash
pip install epistemic-graph-memory[all]
```

## MCP Server

```json
{"mcpServers":{"graph-memory":{"command":"graph-memory-mcp"}}}
```

Streamable HTTP (for OpenCode, Docker, remote agents):

```bash
graph-memory-mcp-http    # http://127.0.0.1:8765/mcp
```

## CLI

### Ingest

```bash
graph-memory ingest-code .                    # full codebase AST + call graphs
graph-memory ingest-file src/engine.py        # single file re-parse (<5ms)
```

### Snapshots

```bash
graph-memory snapshot --max-tokens 600 --min-trust 0.7
```

Output is deterministic and content-fingerprinted — unchanged graph returns identical bytes so prompt caches stay warm.

### Search

```bash
graph-memory search "effective_tr"            # FTS5 + identifier substring fallback
graph-memory search-sessions "trust decay"    # episodic session logs
```

### Decision History

```bash
graph-memory query-history --agent Hermes --days 7
graph-memory contradictions                   # surfaced conflicts between agents
```

### Lifecycle Hooks

```bash
graph-memory hook install                     # auto-configure all 9 frameworks
graph-memory hook install --framework cursor
graph-memory hook status
graph-memory hook refresh                     # re-render snapshots now
```

Supported: Claude Code, ZCode, Cursor, Codex, OpenCode, Antigravity, Qoder, Hermes, Claude Desktop.

Events: PostToolUse (incremental AST ingest <5ms), Stop (transcript distillation + fact extraction), SessionStart (snapshot refresh).

### Import / Export

```bash
graph-memory import-md CLAUDE.md              # markdown sections → Knowledge_Nodes
graph-memory import-mem0 memories.json        # mem0 JSON → Fact_Nodes
graph-memory export-obsidian ~/vault           # Obsidian vault with [[wikilinks]]
```

### Maintenance

```bash
graph-memory prune --days 60                  # soft-delete stale, unreferenced nodes
graph-memory lint --fix                       # orphan/dangling edge cleanup
graph-memory consolidate                       # SQLite vacuum
graph-memory merge <source_id> <target_id>    # entity merge with alias redirect
```

### Visualization

```bash
graph-memory export-html graph.html
graph-memory export-3d graph_3d.html
```

## Node Types

- **Fact_Node**: Ground-truth from AST, Git, filesystem, or session distillation.
- **Knowledge_Node**: Architecture, module summaries, design decisions.
- **Episode_Node**: Completed task sequences (linked with FOLLOWED_BY).
- **Release_Node**: Published software versions.

## Trust Model

Query-time decay: `effective = base × 0.5^(Δdays/30)`. Re-verification (ingest, add_observation) resets to 100%. Stale unreferenced nodes get soft-deleted by `prune`.

## Graph Best Practices

1. **Link new nodes** with `--link-to` to prevent orphans.
2. **Use the standard ontology**: Fact_Node, Knowledge_Node, Episode_Node, Release_Node.
3. **Inject metadata** in attributes JSON: `created_by`, `source`, `confidence`, `verification_source`.
4. **Standard relations**: IMPLEMENTS, DEPENDS_ON, CALLS, DEFINED_IN, EXTENDS, FIXES, PART_OF, FOLLOWED_BY.
5. **Query with `--min-trust 0.6`** to exclude low-confidence data.
