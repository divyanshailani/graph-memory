# Changelog

## [v3.7.1] - 2026-08-16
- **Repo presentation overhaul**: README rewritten to showcase the actual project (architecture, real numbers, no filler). SKILL.md updated from v2.1 boilerplate to v3.7. Egg-info, `__pycache__`, and build artifacts removed from git tracking. `conftest.py` moved to `tests/`. `.gitignore` expanded. `pyproject.toml` given keywords, license, URLs, and an honest description.
- **CHANGELOG compressed**: v1.0–v3.3 collapsed to one-line summaries (full history in git log); v3.6.0+ kept detailed.

## [v3.7.0] - 2026-08-16
- **Batch Ingestion Engine**: One connection + one transaction per file instead of per node. Full-repo ingestion ~17× faster (76s → 4.3s). Unchanged re-ingest via hash-skip: 0.06s.
- **Cross-File Call Graph Resolution**: Post-ingestion pass rewires CALLS stubs to uniquely-named definitions across file boundaries via DEFINED_IN edges. Ambiguous names keep stubs; edge-less stubs cleaned.
- **Contradiction Detection**: Agent-driven upserts that conflict on scalar fields record a capped `conflicts` array. Mechanical AST re-verification is exempt. `graph-memory contradictions` CLI command; snapshots surface top 3 as `⚠ Conflicting Assertions`.
- **Stale-Node GC**: `graph-memory prune` soft-deletes decayed, unreferenced nodes. Project roots never pruned.
- **Real Reflection Engine**: `memory.reflect_session_memory` digests last 30 days of actual Decision_Ledger entries (not static templates) into 5 memory categories.
- **Identifier Substring Search**: `search_nodes` falls back to `LIKE '%q%'` on node IDs. (A trigram FTS5 index was tried and removed — its sync triggers corrupted under WAL on SQLite 3.50.4.)
- **Tests**: 57 passing. Added `tests/test_v3_7_0_scale_teams.py`.

## [v3.6.0] - 2026-08-16
- **Streamable HTTP MCP Transport**: `graph-memory-mcp-http` (default `http://127.0.0.1:8765/mcp`). Stateless session mode for concurrent agents. Unlocks OpenCode, Docker, remote agents. `/health` endpoint. New `http` extra.
- **Memory Importers**: `graph-memory import-md` (markdown sections → Knowledge_Nodes, idempotent). `graph-memory import-mem0` (mem0 JSON → Fact_Nodes, all wrapper formats).
- **Obsidian Vault Export**: `graph-memory export-obsidian <dir>` writes curated knowledge as markdown with YAML frontmatter, observation bullets, and `[[wikilinks]]` for graph edges.
- **Monorepo-Safe `--root` Flag**: `ingest-code` and `ingest-file` accept explicit namespace root for identical node IDs across entrypoints.
- **OpenCode Native MCP**: `hook install --framework opencode` registers remote MCP entry in `opencode.json`.
- **Tests**: Added `test_v3_6_0_open_borders.py`. 50 passing.

## [v3.5.1] - 2026-08-16
- **Hash-Skip Incremental Ingestion**: Unchanged files skip all work — zero writes on untouched re-ingest. `ingest-code` reports `{"parsed": n, "skipped": m}`.
- **Prompt-Stable Snapshots**: Deterministic ordering + content fingerprinting in `Snapshot_Cache` table. Unchanged graph returns byte-identical snapshot.
- **Sweep Root Protection**: All `Project_*` roots protected from orphan sweep.
- **PyPI Publish Automation**: `.github/workflows/publish.yml` via OIDC trusted publishing on `v*` tags.

## [v3.5.0] - 2026-08-16
- **Harness-Agnostic Lifecycle Dispatcher** (`hook-event`): PostToolUse → incremental AST ingest (<5ms); Stop → transcript distillation into graph; SessionStart → snapshot refresh. Silent on success.
- **4 New Framework Integrations**: ZCode (event hooks), Cursor (MCP + rule), Qoder (rule), OpenCode (AGENTS.md section). All idempotent.
- **Claude Code Real Event Hooks**: PostToolUse/Stop/SessionStart in `~/.claude/settings.json`.
- **Codex MCP Registration**: Marker-guarded section in `~/.codex/config.toml`.
- **Snapshot Refresh**: `hook refresh` re-renders all installed snapshots.
- **Bugfixes**: Fresh-database crash on first hook event; installer directory derivation.

## [v3.4.1] - 2026-08-16
- **Decision Ledger Signal Isolation**: AST upserts pass `log_ledger=False` — no more ledger flooding from re-parsing. Agent/MCP/CLI upserts still audited.
- **Bounded Node History**: Capped at 10 entries, consecutive identical entries collapsed.
- **Batched Search Write-Feedback**: Single transaction for access-count bumps.

## [v3.4.0] - 2026-08-16
- **Project-Scoped Node Identity**: Node IDs namespaced by project root + 6-char path hash. Fixes same-basename and cross-project collisions.
- **Import Sanitization**: Relative imports no longer produce junk `External_Dependency` nodes.
- **Root Detection for `ingest-file`**: Single-file ingestion derives same node IDs as `ingest-code`.

## [v3.3.0] - 2026-08-16
- Repo Wiki Generator, Domain Knowledge Cards, Session Memory Reflection Engine (v1), 4 new MCP tools.

## [v3.2.0]–[v3.2.4] - 2026-08-05 to 2026-08-08
- AST ingestion scoping (exclude venv/node_modules), setuptools package discovery fix, circular import elimination, framework hooks export fix.

## [v3.0.0]–[v3.1.0] - 2026-08-05
- Hermes-class snapshot engine, micro-compaction distiller, episodic FTS5 session logging, framework auto-memory bindings (Antigravity, Claude Code, Claude Desktop, Codex, Hermes), cross-platform path resolution, atomic JSON backups.

## [v2.1.0]–[v2.1.2] - 2026-07-28 to 2026-07-29
- Dynamic epistemic trust decay (Ebbinghaus forgetting curve), `Decision_Ledger` table, `query_decision_history` MCP tool, effective trust threaded into search filtering, tree-sitter multi-tier fallback, stub node auto-creation.

## [v2.0.0]–[v2.0.1] - 2026-07-20
- Function call graph extraction (CALLS), class inheritance (EXTENDS), pre-sweep ghost pruning, TSX/JSX support, cybersecurity QA hardening (10MB file cap, binary detection, recursion depth cap).

## [v1.6.8]–[v1.9.0] - 2026-07-12 to 2026-07-20
- Safe entity merging with alias redirection, graph hygiene linting, database consolidation, strict node ontology, code-aware AST extraction (signatures, docstrings, line ranges), `ingest_file` MCP tool.

## [v1.0.0]–[v1.2.0] - 2026-07-11 to 2026-07-12
- Initial release. SQLite WAL engine, trust-weighted verification, vis.js export, MCP server, PyPI distribution, 9 standard Anthropic MCP tool signatures, `write_transaction` context manager.
