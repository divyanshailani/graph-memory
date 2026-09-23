# Changelog

## [v3.8.3] - 2026-09-23
- **Snapshot Visibility Fix**: the candidate pool was `ORDER BY id ASC LIMIT 50` applied *before* trust filtering, so past 50 nodes the snapshot only ever saw the alphabetically first IDs — on this repo's own 767-node graph, knowledge cards sat at position 754 and release milestones at 765, and the `## Project Milestones & Releases` section could never render. Candidates are now ranked in SQL by trust and recency within a bounded pool (2000) and filtered by exact effective trust in Python; sections rank curated knowledge, then prose facts, then bare identifiers, and nodes carrying nothing but their own ID (files, external deps) no longer consume the injection budget. Release entries render as `v3.8.2 "Polish": first change (+4 more)` instead of a Python list repr. Ordering stays deterministic — unchanged graph still returns byte-identical text.
- **Hash-Stable Re-Verification**: new `engine.reverify_hash_stable_nodes()` re-verifies AST-derived facts whose source file is byte-identical to the hash recorded at ingest — derived facts are still true if the file did not change, so verification needs no agent and no test run. File-less derived nodes (call stubs, import targets, directory MOCs, the project root) are verified by evidence instead: a node is re-verified only when every derived node feeding it is verified, so a changed file correctly keeps its dependents decayed. Agent-authored nodes are never touched — a curated card, release node or distilled fact is an assertion that no file proves, and an agent's link to the project root is not derivation evidence. Writes only `trust_score`/`last_verified_at`/`verification_method` (node payloads and snapshot bytes do not churn), and no `Decision_Ledger` rows (mechanical, not an agent decision — same signal isolation as v3.4.1). Wired into `refresh_installed_snapshots()`, so the SessionStart/Stop hooks keep an idle graph from decaying out of its own memory, plus `graph-memory snapshot --reverify` for manual runs. On this repo's own graph, simulating 200 days idle moves 795/795 nodes below the 0.6 search floor; one pass restores 717 of them and leaves exactly the curated nodes plus the files that genuinely changed. This closes the "no automated verification cron" gap in ISSUES.md.
- **Tests**: 66 passing (2 added: `tests/test_v3_8_3_snapshot_reverify.py`).

## [v3.8.2] - 2026-09-07
- **Version Visibility**: `graph_memory.__version__` exposed and `graph-memory --version` prints it (e.g. `graph-memory 3.8.2`). Previously the version lived only in `pyproject.toml`.
- **`add_node` Input Validation**: Empty/whitespace `node_id` or `label`, malformed JSON, and non-object properties are rejected with clear errors before touching the graph. Previously any typo (e.g. a stray `add_node ok x`) became a permanent node.
- **CI**: Python 3.14 added to the test matrix (3.10–3.14).
- **Docs**: README Numbers table updated to actual counts (5,436 source lines, 1,674 test lines, 64 tests).
- **Tests**: 64 passing. Added `tests/test_v3_8_2_cli_validation.py`.

## [v3.8.1] - 2026-08-22
- **Stdlib-only core (Android/Termux fix)**: `mcp` and `tree-sitter` moved out of required dependencies into optional extras. The core package (`graph-memory`, search, snapshot, Markdown/mem0 import, Obsidian export, reflection, hooks) now installs anywhere with zero compiled dependencies — fixing the multi-minute `pydantic-core` Rust build stall on Android where the target triple is unsupported. New extras: `[mcp]`, `[ast]`, plus per-language `[python]`/`[typescript]`/`[javascript]`/`[go]`/`[rust]` now correctly include the `tree-sitter` core package. `[http]` now pulls `mcp` explicitly.
- **Graceful degradation**: MCP entrypoints (`graph-memory-mcp`, `graph-memory-mcp-http`) print a one-line install hint instead of an `ImportError` traceback when their extra is missing. AST ingestion returns a clear error when `tree-sitter` is absent.
- **CI**: test + publish workflows install the `[all]` extra; the publish smoke test now verifies the stdlib-only wheel installs and that MCP degrades gracefully.

## [v3.8.0] - 2026-08-19
- **MCP Dependency Fix**: Pinned `mcp>=1.28,<2` to prevent incompatibility with MCP 2.x (fixes clean install failures)
- **HTTP Transport Security**: Added DNS rebinding protection, optional API key authentication via `GRAPH_MEMORY_API_KEY`, and security warnings for remote deployment
- **Incremental Ingestion Edge Cleanup**: Fixed ghost CALLS/EXTENDS/IMPORTS edges when code structure changes; `ingest_file` now calls edge cleanup and cross-file resolution
- **MCP Error Handling**: Proper error responses with `isError=True` flag instead of plain text content
- **Batch MCP Mutations**: New atomic batch functions (`batch_create_entities`, `batch_create_relations`, `batch_add_observations`) with single-transaction semantics
- **Pre-Publish CI Validation**: Tests, twine check, and smoke tests now run before PyPI publish
- **Python Version Matrix**: CI now tests Python 3.10, 3.11, 3.12, and 3.13
- **Documentation Updates**: Corrected tool/command counts (19 MCP tools, 28 CLI commands), fixed zsh install command quoting
- **Package Discovery**: Fixed setuptools configuration to exclude tests from wheel distribution

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
