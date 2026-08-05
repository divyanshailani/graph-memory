# Changelog

All notable changes to the Graph-Memory project will be documented in this file.

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
