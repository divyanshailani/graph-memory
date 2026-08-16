# Changelog

All notable changes to the Graph-Memory project will be documented in this file.

## [v3.5.0] - 2026-08-16
- **Harness-Agnostic Lifecycle Dispatcher (`graph_memory/core/lifecycle.py`)**: New `graph-memory hook-event` command reads a JSON hook payload from stdin and dispatches it — `PostToolUse` auto-ingests the edited file (<5ms incremental AST), `Stop`/`SessionEnd` logs the transcript tail into FTS5 Session_Logs and distills `[Fact:]`/`[Decision:]` markers into graph facts, and `SessionStart` refreshes every installed snapshot file. Silent on success (compatible with strict hook output schemas like ZCode's); never raises into the host harness.
- **Four New Framework Integrations**: `zcode` (event hooks in `~/.zcode/cli/config.json` with `hooks.enabled: true`, portable `process`-type entries), `cursor` (MCP registration in `~/.cursor/mcp.json` + `alwaysApply` rule with lifecycle protocol), `qoder` (rule file in `~/.qoder/rules/`), and `opencode` (marked auto-section in `AGENTS.md`, no config clobbering). All installs are idempotent and preserve existing user configuration.
- **Claude Code Real Event Hooks**: `hook install --framework claude-code` now merges PostToolUse/Stop/SessionStart hooks into `~/.claude/settings.json` (atomic write with backup) in addition to the auto-context file; uninstall removes them cleanly.
- **Codex MCP Registration**: Codex install now appends a marker-guarded `[mcp_servers.graph-memory]` section to `~/.codex/config.toml` alongside the snapshot rule.
- **Snapshot Refresh Lifecycle (`graph-memory hook refresh` + `refresh_installed_snapshots`)**: Every installed framework's snapshot file is re-rendered from the live graph — by the SessionStart/Stop hooks automatically, or manually — so injected memory never goes stale. Hermes re-syncs its `MEMORY.md` section.
- **Lifecycle Protocol Instructions**: All instruction-file integrations (Antigravity, Claude Code, Codex, Cursor, Qoder, OpenCode, Hermes) now embed a four-step protocol (snapshot at start, `ingest_file` after edits, `distill_session` before ending, search the Decision Ledger before re-deciding) so agents self-manage the loop even without system hooks.
- **Bugfix — Fresh-Database Crash**: `ingest_file` ran `pre_sweep_file_components` before schema initialization and crashed with "no such table: Nodes" on a brand-new database (exactly the first-hook-event scenario). Both ingestion entrypoints now call `init_db` first.
- **Bugfix — Installer Directory Derivation**: Framework installers create their target directory from the file path itself, so patched/relocated config paths work correctly.
- **Regression Tests**: Added `test_v3_5_lifecycle_hooks.py` (6 tests: auto-ingest, tool filtering, transcript capture + distillation, ZCode idempotent install/uninstall, Cursor + Claude Code installs, SessionStart refresh) and updated framework count assertions. 41 tests passing.

## [v3.4.1] - 2026-08-16
- **Decision Ledger Signal Isolation**: `get_or_create_node` now accepts `log_ledger` (default `True`). AST ingestion upserts pass `log_ledger=False` — deterministic re-parsing is not an agent decision, so a full `ingest-code` run no longer floods the `Decision_Ledger` with thousands of "Node created or updated" rows. Agent/MCP/CLI-driven upserts, observations, and merges continue to be audited; AST provenance still lands in node `history` and properties.
- **Bounded Node History**: Node `history` arrays are capped at `MAX_NODE_HISTORY` (10) entries and consecutive identical entries (same agent, action, rationale) are collapsed, so repeated re-ingestion of an unchanged file no longer grows the properties JSON payload.
- **Batched Search Write-Feedback**: `search_nodes` now bumps `access_count` for all matched nodes in a single write transaction instead of one transaction per result row, removing write amplification from the read path.
- **Regression Tests**: Added `test_v3_4_1_write_amplification.py` covering ledger-free ingestion, agent-decision auditing, history cap/dedupe, and batched access-count feedback.

## [v3.4.0] - 2026-08-16
- **Project-Scoped Node Identity Scheme**: Node IDs are now namespaced by project root (`<name>_<6-char path hash>`) and keyed by repo-relative POSIX paths (`File_<ns>/graph_memory/core/engine.py`, `Func_load_<ns>/a/utils.py`, `MOC_<ns>/graph_memory/core`, `Dependency_<ns>/<module>`). Fixes two classes of silent node collision in the legacy basename-only scheme: identical basenames in different directories (`a/utils.py` vs `b/utils.py`) and identical relative paths across projects sharing one database.
- **Import Sanitization (`sanitize_import_module`)**: Relative Python imports (`from . import x`, `from ...pkg import y`) and relative JS/TS paths (`./x`, `../y`) no longer produce `External_Dependency` nodes; leading dots are stripped from valid relative module paths, eliminating junk nodes like `Dependency_.` and `Dependency_...transformers.models`.
- **Root Detection for `ingest-file` (`_find_project_root`)**: Single-file incremental ingestion now resolves the enclosing project root via marker files (`.git`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`) so `ingest-file` and `ingest-code` derive identical node IDs for the same file. File and Component nodes now store consistent relative `file_path`, plus `abs_path` and `project_root` provenance properties.
- **Regression Tests**: Added `test_v3_4_id_namespacing.py` covering same-basename collisions, cross-project collisions, `ingest-file`/`ingest-code` identity agreement, and import sanitization.

## [v3.3.0] - 2026-08-16
- **Automated Repo Wiki Generator (`graph_memory/core/knowledge.py`)**: Generates hierarchical Markdown documentation trees under `.agents/wiki/codebase/` with exact Qoder frontmatter schemas (`layout_version`, `module_id`, `source_files`), structured sections, and relation graphs.
- **Domain Knowledge Card Extractor**: Classifies codebase facts into 8 standardized software knowledge domains (`frontend_style`, `backend_architecture`, `build_system`, `logging_system`, `configuration_system`, `dependency_management`, `error_handling`, `external_dependency`).
- **Session Memory Reflection Engine (`graph_memory/core/memory.py`)**: Analyzes decision ledger history and active facts to reflect learnings into 5 persistent memory categories under `.agents/memories/`.
- **4 New MCP Tools**: Added `generate_repo_wiki`, `get_knowledge_cards`, `reflect_session_memory`, and `search_repo_wiki` to the MCP Server.
- **New CLI Commands**: `graph-memory wiki generate`, `graph-memory knowledge extract`, `graph-memory memory reflect`.

## [v3.2.4] - 2026-08-08
- **AST Ingestion Scoping Isolation**: Implemented `should_ignore_path` in `graph_memory/core/ingest.py` to strictly exclude third-party dependencies, virtual environments (`venv`, `.venv`, `env`, `site-packages`), `node_modules`, `dist`, `build`, `target`, and cache directories from AST graph ingestion.
- **Stale Graph Memory Correction**: Updated Package node `epistemic-graph-memory` metadata in active project database to reflect `v3.2.4` global PyPI release state.
- **Setuptools Package Discovery Fix**: Configured `tool.setuptools.packages.find` in `pyproject.toml` to automatically bundle all subpackages (`graph_memory.core`, `graph_memory.mcp`, `graph_memory.integrations`), ensuring 100% complete global wheel installations across all platforms.
- **Circular Import Elimination**: Cleaned `graph_memory/integrations/__init__.py` and updated `cli.py` to perform explicit direct module imports for `framework_hooks`, ensuring 100% clean global execution across global system interpreters.

## [v3.2.3] - 2026-08-05
- **Setuptools Package Discovery Fix**: Configured `tool.setuptools.packages.find` in `pyproject.toml` to automatically bundle all subpackages (`graph_memory.core`, `graph_memory.mcp`, `graph_memory.integrations`), ensuring 100% complete global wheel installations across all platforms.
- **Circular Import Elimination**: Cleaned `graph_memory/integrations/__init__.py` and updated `cli.py` to perform explicit direct module imports for `framework_hooks`, ensuring 100% clean global execution across global system interpreters.

## [v3.2.2] - 2026-08-05
- **Circular Import Elimination**: Cleaned `graph_memory/integrations/__init__.py` and updated `cli.py` to perform explicit direct module imports for `framework_hooks`, ensuring 100% clean global execution across global system interpreters.

## [v3.2.1] - 2026-08-05
- **Global Package Integration Export Fix**: Added `from . import framework_hooks` in `graph_memory/integrations/__init__.py` to resolve global package import resolution across global system environments.
- **Enterprise Cross-Platform Robustness**: Dynamic multi-OS path resolution for Windows (`%APPDATA%`), macOS (`~/Library/Application Support`), and Linux (`XDG_CONFIG_HOME` / `~/.config`).
- **Atomic File Backups & Zero-Corruption Guarantee**: Implemented `atomic_write_json` with automated timestamped `.bak` backups before modifying JSON configurations, ensuring safe atomic replaces (`tempfile` + `os.replace`).
- **Graceful Exception Boundaries**: Framework hooks catch missing paths, permission denials, and malformed files gracefully, returning structured `{"status": "skipped", "message": "..."}` without throwing unhandled exceptions or breaking agent execution.
- **Framework Auto-Memory Bindings (`graph-memory hook`)**: Introduced optional, user-controlled framework hooks for Antigravity, Claude Code CLI, Claude Desktop, Codex, and Hermes.
- **Claude Desktop AUTO-SNAPSHOT**: Prepends dynamic active memory snapshot to seed context when `GRAPH_MEMORY_AUTO_SNAPSHOT=1` is set in MCP configuration.
- **Non-Breaking Safety Guarantee**: Hooks operate purely via non-destructive sidecar rules, skill Markdown files, and MCP env flags, preserving 100% native stability.
- **CLI Commands**: Added `graph-memory hook install`, `graph-memory hook uninstall`, and `graph-memory hook status`.

## [v3.2.0] - 2026-08-05
- **Enterprise Cross-Platform Robustness**: Dynamic multi-OS path resolution for Windows (`%APPDATA%`), macOS (`~/Library/Application Support`), and Linux (`XDG_CONFIG_HOME` / `~/.config`).
- **Atomic File Backups & Zero-Corruption Guarantee**: Implemented `atomic_write_json` with automated timestamped `.bak` backups before modifying JSON configurations, ensuring safe atomic replaces (`tempfile` + `os.replace`).
- **Graceful Exception Boundaries**: Framework hooks catch missing paths, permission denials, and malformed files gracefully, returning structured `{"status": "skipped", "message": "..."}` without throwing unhandled exceptions or breaking agent execution.
- **Framework Auto-Memory Bindings (`graph-memory hook`)**: Introduced optional, user-controlled framework hooks for Antigravity, Claude Code CLI, Claude Desktop, Codex, and Hermes.
- **Claude Desktop AUTO-SNAPSHOT**: Prepends dynamic active memory snapshot to seed context when `GRAPH_MEMORY_AUTO_SNAPSHOT=1` is set in MCP configuration.
- **Non-Breaking Safety Guarantee**: Hooks operate purely via non-destructive sidecar rules, skill Markdown files, and MCP env flags, preserving 100% native stability.
- **CLI Commands**: Added `graph-memory hook install`, `graph-memory hook uninstall`, and `graph-memory hook status`.

## [v3.1.0] - 2026-08-05
- **Framework Auto-Memory Bindings (`graph-memory hook`)**: Introduced optional, user-controlled framework hooks for Antigravity, Claude Code CLI, Claude Desktop, Codex, and Hermes.
- **Claude Desktop AUTO-SNAPSHOT**: Prepends dynamic active memory snapshot to seed context when `GRAPH_MEMORY_AUTO_SNAPSHOT=1` is set in MCP configuration.
- **Non-Breaking Safety Guarantee**: Hooks operate purely via non-destructive sidecar rules, skill Markdown files, and MCP env flags, preserving 100% native stability.
- **CLI Commands**: Added `graph-memory hook install`, `graph-memory hook uninstall`, and `graph-memory hook status`.

## [v3.0.0] - 2026-08-05
- **Hermes-Class Declarative Snapshot Engine**: Added `graph_memory/core/snapshot.py` and `get_active_snapshot` MCP tool to generate ultra-dense, 500-token prompt-cache friendly Markdown snapshots of high-trust facts for automatic prompt injection on session startup.
- **Asymmetric Continuous Micro-Compactor & Distiller**: Added `graph_memory/core/distill.py` and `distill_session` MCP tool to absorb large assistant tool outputs and distill them into structured graph facts while preserving verbatim user intent.
- **Episodic Session Logging & FTS5 Search**: Added `Session_Logs` table, `Session_Logs_fts` virtual table, and `search_session_logs` engine function for searching historic conversation logs.
- **CLI Subcommands**: Added `graph-memory snapshot` and `graph-memory search-sessions` subcommands.

## [v2.1.2] - 2026-07-29
- **Multi-Tier Tree-Sitter Language Package Fallback**: Refined `load_parser` in `ingest.py` with a multi-tier fallback resolution chain for extension-specific language functions (e.g. `language_tsx`, `language_jsx`, `language_typescript`), extension clean names, package suffixes, and generic `language()`, providing zero-crash compatibility across all old and new tree-sitter packages.
- **Foreign Key Edge Stub Protection**: Added auto-creation of stub nodes in `get_or_create_node` and `create_relation` to maintain foreign key integrity when ingesting call graph edges to external standard library or un-parsed methods.

## [v2.1.1] - 2026-07-28
- **Fixed `timedelta` NameError**: Added `timedelta` to top-level `datetime` imports in `engine.py` to fix runtime `NameError` on `query_decision_ledger(days=N)` query path.
- **Effective Trust Threaded into Search Filtering**: Updated `search_nodes` to compute dynamic `calculate_effective_trust` for each candidate result and filter out stale entities below `min_trust` threshold.
- **Effective Trust Threaded into Subgraph & Edge Retrieval**: Updated `serialize_subgraph` central node check and relationship traversal to calculate dynamic effective trust for central nodes and directional edges, ensuring retrieval filters reflect time-decayed truth.

## [v2.1.0] - 2026-07-28
- **Dynamic Epistemic Truth Decay (Ebbinghaus Forgetting Curve)**: Added `calculate_effective_trust` and `get_effective_trust_for_node` to compute time-decayed trust score dynamically based on elapsed time since `last_verified_at` ($\text{effective\_trust} = \text{base\_trust} \times 0.5^{\frac{\Delta t}{30.0}}$).
- **First-Class `Decision_Ledger` Table**: Created dedicated, indexed `Decision_Ledger` table in SQLite schema to log agent, node_id, action, rationale, and ISO timestamp.
- **`query_decision_history` MCP Tool & CLI Subcommand**: Added `query_decision_history` MCP tool and `graph-memory query-history` CLI subcommand to query decisions globally across the entire project by agent, node ID, or timeframe.
- **Effective Trust Formatting in Subgraphs**: Updated `serialize_subgraph` to display effective trust and decay rate alongside decision history.

## [v2.0.1] - Cybersecurity QA Hardening & Edge-Case Protection
- **Memory Explosion Protection**: Added 10MB file size cap (`MAX_FILE_SIZE = 10MB`) to prevent AST parsing memory exhaustion or ReDoS attacks.
- **Null Byte Binary File Protection**: Added `b'\x00'` sample checks to safely ignore binary executable files.
- **Recursion Stack Overflow Cap**: Enforced `max_depth = 100` cap in recursive AST traversals (`extract_entities` and `extract_calls_and_inheritance`).
- **Soft-Deleted Node Reactivation**: Updated `get_or_create_node` to reactivate pruned nodes (`is_deleted = 0, status = 'active'`) when re-discovered during re-parsing.

## [v2.0.0] - Production Call Graphs, Class Inheritance & Pre-Sweep Component Pruning
- **Function Call Graph Extraction (`CALLS`)**: Enhanced AST parsing (`ingest.py`) to extract function and method call trees (`Func_A -[CALLS]-> Func_B`) across Python, TS, JS, Go, and Rust.
- **Class Inheritance Extraction (`EXTENDS`)**: Extracted class inheritance hierarchies (`Class_Sub -[EXTENDS]-> Class_Base`) for Python superclasses and TS/JS class heritage.
- **Pre-Sweep Ghost Component Pruning (`pre_sweep_file_components`)**: Automatically soft-deletes obsolete component nodes before re-parsing modified files, completely eliminating ghost nodes from the graph.
- **React TSX & JSX Support**: Added native AST parsing for `.tsx` and `.jsx` files.
- **Multi-Agent Ingestion Provenance**: Enabled passing `agent_name` and `rationale` through full project and single-file ingestions.

## [v1.9.0] - Code-Aware AST Ingestion, Agent Provenance Ledger & Two-Way Sync
- **Code-Aware AST Extraction**: Enhanced Tree-sitter ingestion (`ingest.py`) to capture function/class signatures, docstrings, 1-indexed line ranges (`L10-L45`), and code snippet previews directly into node metadata.
- **Agent Provenance & Decision Rationale Ledger**: Added mandatory agent attribution (`author_agent`, `last_modified_by`), decision reasoning (`rationale`, `design_intent`), and append-only decision logs (`history: []`) across nodes and observations (aligning with IETF Agent Audit Trail standards).
- **Two-Way Incremental Sync (`ingest_file`)**: Added `ingest_file(file_path)` MCP tool and CLI command (`graph-memory ingest-file`) to re-parse a single changed file into the graph in <5ms.
- **MCP Extensions**: Added `read_code_snippet` and `ingest_file` tools to the MCP server (`server.py`).

## [v1.8.0] - Safe Entity Resolution, Node Merging & Alias Redirection
- **Safe Node Merging (`merge_nodes` / `graph-memory merge`)**: Introduced atomic entity merging that consolidates JSON observations, metadata, and aliases, rewires all directional edges, and prevents self-loop creation or SQLite composite unique constraint collisions.
- **Recursive Alias Pointer Redirection**: Updated `serialize_subgraph` and `get_node` to follow `merged_into` pointers with a `visited` set and depth cap, seamlessly resolving queries on merged node IDs to their canonical targets with an `[Alias Redirect]` tag.
- **MCP `merge_entities` Tool**: Added standard Anthropic MCP tool signature `merge_entities(sourceName, targetName)` for real-time agentic deduplication.

## [v1.7.0] - Dynamic Seed Memory, Graph Hygiene Linting & Consolidation
- **Dynamic Seed Memory Ingestion**: Injected lightweight active node/hub context into MCP tool signatures (`search_nodes`, `read_graph`) to eliminate AI "Cold Start" amnesia.
- **Graph Hygiene (`graph-memory lint [--fix]`)**: Added a deterministic CLI command to detect orphan nodes and dangling edges, with an automated `--fix` flag for repair.
- **Database Consolidation (`graph-memory consolidate`)**: Added on-demand database maintenance ("Dreaming") to clean dangling relations and execute `PRAGMA incremental_vacuum`.
- **Enrich-Before-Create (Duplicate Guard)**: Enhanced engine property update logic to prevent entity duplication during node assertion.

## [v1.6.8] - Advanced Protocol Schema & Local LLMs
- **Strict Node Ontology (`Fact_Node`)**: Hardcoded the AST ingestion engine (`ingest.py`) to exclusively emit deterministic `Fact_Node` entities. Legacy granular types (`Component`, `File`) have been moved into the strict JSON schema payload.
- **Advanced Agent Protocols**: Introduced `[attributes_json]` schema enforcement for Multi-Agent Provenance (`created_by`, `source`) and Expanded Trust (`confidence`, `verification_source`).
- **Execution Workflows**: Added native support for `Episode_Node` tracking to allow agents to log successful macro-workflows via `FOLLOWED_BY` edges.
- **Local LLM Integration**: Fully documented MCP compatibility and schema enforcement for local agents (Ollama, LM Studio, OpenHands).
- **Documentation Refactor**: Deleted `THESIS.md` and stripped AI-hype jargon from `README.md` and `SKILL.md` in favor of a clean, technical Open Knowledge Format (OKF) lineage.

## [v1.2.0] - PyPI Global Package & Core Upgrade
- **PyPI Distribution**: Graph-Memory is now an installable global Python package via `pip install graph-memory`. No more cloning!
- **Drop-In MCP Replacement**: Completely rewrote the `mcp/server.py` to expose exactly the 9 standard Anthropic API tool signatures (`create_entities`, `search_nodes`, etc.). Agents no longer need prompt modifications to use Graph-Memory!
- **SQLite Performance & Scale**: 
  - Enabled `PRAGMA auto_vacuum = INCREMENTAL` for instant disk reclamation upon node decay.
  - Implemented `check_same_thread=False` to natively support multi-agent async environments.
  - Added a `write_transaction` context manager using `BEGIN IMMEDIATE` to queue concurrent writes in WAL mode.
- **Supersession Conflict Tracking**: Fact changes now trigger proper `status='superseded'` workflows instead of destructive overwrites.
- **Soft Deletes**: Deleting nodes now flips an `is_deleted = 1` boolean to preserve the timeline, rather than wiping the row.
- **JSON Expression Indexing**: Built a generic B-Tree index into the FTS5 payload to speed up metadata lookups across million-node graphs.

## [v1.1.0] - Trust Tiers & Visuals
- **Visual Trust Tiers**: The `export_html` visualization now renders untrusted, unverified, or stale nodes (older than 3 days) in a distinctly vibrant red color profile.
- **Node Pruning**: Added the `delete_node` CLI command to cleanly remove hallucinated or incorrect entities.
- **Data Validation Bug Fix**: Fixed a silent bug where nodes created exclusively via the `add_relation` tool bypassed the strict JSON properties constraints, causing serialization crashes when the visualizer encountered null payloads.
- **CLI Robustness**: Overhauled `memory_tool.py` argument parsing to handle empty/null JSON injections without throwing a `json.decoder.JSONDecodeError`.

## [v1.0.0] - Initial Release
- **Core Memory Engine**: Implemented the `db.py` SQLite engine using `PRAGMA journal_mode = WAL` and an Epistemic Graph schema.
- **Trust-Weighted Verification**: Added strict `verification_method` requirements (`assumed` vs `source_read` vs `user_explicit`) to node and relationship assertions.
- **Dynamic Vis.js Export**: Created a basic physics-based node visualization with drag-and-drop mechanics.
- **MCP Server Configuration**: Set up basic integration points for Claude Desktop and Cursor.
