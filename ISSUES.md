# Known Issues & Future Enhancements

## Known Issues
- **Staleness Color Rendering Overrides Groups**: Currently, when a node is marked as "stale" or "unverified", its custom red/orange styling overrides its default Group color (e.g., Infrastructure, Task). This makes it harder to identify the node type at a glance.
- **OpenCode Limitations**: OpenCode currently only supports remote MCP servers over HTTP/SSE, meaning it cannot run the `mcp_server.py` as a local command.

## Future Enhancements
- **Automated Verification Crons**: Implement a background task that periodically runs the test suite and automatically bumps the `last_verified_at` timestamp for related nodes if the tests pass.
- **Pruning**: Add a tool to archive or delete nodes that have been stale for over 30 days without any incoming edges.
- **Deeper Obsidian Integration**: Generate full bidirectional markdown links for attributes in the Obsidian export, instead of just dumping JSON blocks.
