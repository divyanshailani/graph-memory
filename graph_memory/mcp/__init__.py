"""
MCP transport entrypoints.

`mcp` is an optional dependency — it pulls in pydantic, whose `pydantic-core`
needs a Rust build and has no prebuilt wheel on some platforms (e.g. Android
under Termux). The graph-memory core is stdlib-only, so the MCP transport is
lazily imported here: the console scripts point at this module's `main` /
`main_http`, and only import the real server when `mcp` is actually installed.
"""

_HTTP_ERROR_HINT = (
    "[!] The HTTP MCP transport requires the optional 'http' (or 'mcp') extra.\n"
    "    Install it with:  pip install 'epistemic-graph-memory[http]'"
)

_STDIO_ERROR_HINT = (
    "[!] The MCP transport requires the optional 'mcp' extra.\n"
    "    Install it with:  pip install 'epistemic-graph-memory[mcp]'"
)


def main():
    try:
        from graph_memory.mcp.server import main as _main
    except ImportError as e:
        raise SystemExit(f"{_STDIO_ERROR_HINT}\n    (underlying error: {e})")
    return _main()


def main_http():
    try:
        from graph_memory.mcp.http_server import main as _main
    except ImportError as e:
        raise SystemExit(f"{_HTTP_ERROR_HINT}\n    (underlying error: {e})")
    return _main()
