# Known Issues & Future Enhancements

## Known Issues
- **Staleness Color Rendering Overrides Groups**: Currently, when a node is marked as "stale" or "unverified", its custom red/orange styling overrides its default Group color (e.g., Infrastructure, Task). This makes it harder to identify the node type at a glance.
- **Local-Variable Receivers Stay Unresolved**: v3.9.0 resolves calls through import bindings (module/package scope). Receivers that are local variables or parameters (`conn.execute(...)`, `self.helper(...)` without an import binding) have no module to resolve against, so those CALLS edges keep their stub. On this repo's own graph that residual is ~45% of CALLS edges; data-flow or LSP-backed resolution is the next step.

## Resolved (historical)
- ~~**OpenCode Limitations**: OpenCode only supports remote MCP servers over HTTP/SSE~~ — **Resolved in v3.6.0**: `graph-memory-mcp-http` provides a streamable HTTP transport, and `hook install --framework opencode` registers the remote entry in `opencode.json`.
- ~~Node ID collisions across directories/projects~~ — **Resolved in v3.4.0** (project-scoped namespaced IDs).
- ~~Decision Ledger flooded by mechanical AST upserts~~ — **Resolved in v3.4.1** (`log_ledger=False` for ingestion).
- ~~**Cross-File Call Resolution is Name-Based**~~ — **Resolved in v3.9.0**: CALLS edges carry `receivers`, File nodes carry import `bindings`, and the post-pass resolves through module scope. `np.dot` lands on a `Dependency/numpy.dot` member node instead of any in-project `dot`; `from json import loads; loads()` prefers the binding over the unique-name rule. Uniquely-named in-project calls still resolve as before; ambiguity keeps the stub.

## Future Enhancements
- **Deeper Obsidian Integration**: Generate full bidirectional markdown links for attributes in the Obsidian export, instead of just the Links section.
