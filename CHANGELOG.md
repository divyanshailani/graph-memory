# Changelog

All notable changes to the Graph-Memory project will be documented in this file.

## [v1.1.0] - 2026-07-11
### Added
- **Trust-Weighted Epistemic Graph**: Upgraded the memory graph to track both *when* a node was verified and *how* strong that verification was.
  - Added strict `verification_method` enums (`source_read`, `test_executed`, `endpoint_tested`, `agent_self_report`, `assumed`).
  - Added `created_at` and `last_verified_at` metadata injection to nodes and edges.
  - `last_verified_at` will now **only** update if a "strong" verification method is used. Self-reporting and guessing will no longer reset the staleness clock.
- **Visual Trust Tiers**: The `export_html` visualization now renders untrusted, unverified, or stale nodes (older than 3 days) in a distinctly vibrant red color profile.
- **Node Pruning**: Added `delete_node` functionality across the CLI, MCP Server, and SQLite DB to allow manual pruning of hallucinated or test nodes.

### Fixed
- **Read-Only FS Crash**: Fixed a severe bug where the MCP server crashed when running under Claude Desktop. The DB was previously trying to initialize in the root directory `/`. The server now accepts `workspace_dir` as an explicit parameter in all tools.
- **JSON Empty String Bug**: Hardened the MCP server to gracefully fallback to `{}` when an agent incorrectly passes an empty string `""` to the attributes argument, preventing a `JSONDecodeError` crash.
- **Dummy Node Timestamps**: Fixed an issue where "assumed" dummy nodes created dynamically via `add_relation` were missing their `created_at` timestamps.

## [v1.0.0] - Initial Release
- Initial release of Graph-Memory with `add_node`, `add_relation`, `get_node`, and `export_html` functionality.
- Model Context Protocol (MCP) server implementation for Claude Desktop, Codex, and OpenCode compatibility.
