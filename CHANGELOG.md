# Changelog

All notable changes to the Graph-Memory project will be documented in this file.

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
