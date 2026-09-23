# Known Issues & Future Enhancements

## Known Issues
- **Staleness Color Rendering Overrides Groups**: Currently, when a node is marked as "stale" or "unverified", its custom red/orange styling overrides its default Group color (e.g., Infrastructure, Task). This makes it harder to identify the node type at a glance.
- **Cross-File Call Resolution is Name-Based**: v3.7.0 resolves CALLS stubs to uniquely-named definitions in the same project namespace. Overloaded/aliased callees with multiple definitions are left as stubs (no scope-aware resolution yet).

## Resolved (historical)
- ~~**OpenCode Limitations**: OpenCode only supports remote MCP servers over HTTP/SSE~~ — **Resolved in v3.6.0**: `graph-memory-mcp-http` provides a streamable HTTP transport, and `hook install --framework opencode` registers the remote entry in `opencode.json`.
- ~~Node ID collisions across directories/projects~~ — **Resolved in v3.4.0** (project-scoped namespaced IDs).
- ~~Decision Ledger flooded by mechanical AST upserts~~ — **Resolved in v3.4.1** (`log_ledger=False` for ingestion).

## Future Enhancements
- **Scope-Aware Cross-File Calls**: Resolve calls via import/scope analysis (or LSP) instead of unique-name matching, handling overloads and aliases. (63% of CALLS edges are still unresolved stubs on this repo's own graph.)
- **Test-Driven Re-Verification of Curated Nodes**: The hash-stable pass (v3.8.3) mechanically re-verifies AST-derived facts whose source file is unchanged, but curated knowledge cards and release nodes have no file to hash — re-verifying those still needs an agent or a human. A test-suite-driven pass (bump `last_verified_at` for nodes tied to passing tests) is the remaining piece.
- **Stable Project Identity**: Node IDs are namespaced by a hash of the resolved project path, and `.agents/` is gitignored — so moving or cloning the repo re-keys every node and forces a full re-ingest. A committed `.agents/project_id` would make the store survive relocation.
- **Deeper Obsidian Integration**: Generate full bidirectional markdown links for attributes in the Obsidian export, instead of just the Links section.
- **DB Schema Versioning**: Add an explicit schema_version table with ordered migrations instead of try/except ALTERs.
