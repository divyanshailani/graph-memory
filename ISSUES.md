# Known Issues & Future Enhancements

## Known Issues
- **Staleness Color Rendering Overrides Groups**: Currently, when a node is marked as "stale" or "unverified", its custom red/orange styling overrides its default Group color (e.g., Infrastructure, Task). This makes it harder to identify the node type at a glance.
- **Cross-File Call Resolution is Name-Based**: v3.7.0 resolves CALLS stubs to uniquely-named definitions in the same project namespace. Overloaded/aliased callees with multiple definitions are left as stubs (no scope-aware resolution yet).

## Resolved (historical)
- ~~**OpenCode Limitations**: OpenCode only supports remote MCP servers over HTTP/SSE~~ — **Resolved in v3.6.0**: `graph-memory-mcp-http` provides a streamable HTTP transport, and `hook install --framework opencode` registers the remote entry in `opencode.json`.
- ~~Node ID collisions across directories/projects~~ — **Resolved in v3.4.0** (project-scoped namespaced IDs).
- ~~Decision Ledger flooded by mechanical AST upserts~~ — **Resolved in v3.4.1** (`log_ledger=False` for ingestion).

## Future Enhancements
- **Scope-Aware Cross-File Calls**: Resolve calls via import/scope analysis (or LSP) instead of unique-name matching, handling overloads and aliases.
- **Automated Verification Crons**: Implement a background task that periodically runs the test suite and automatically bumps the `last_verified_at` timestamp for related nodes if the tests pass.
- **Deeper Obsidian Integration**: Generate full bidirectional markdown links for attributes in the Obsidian export, instead of just the Links section.
- **DB Schema Versioning**: Add an explicit schema_version table with ordered migrations instead of try/except ALTERs.
