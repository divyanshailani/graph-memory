"""
Streamable-HTTP MCP transport (v3.6.0 "Open Borders").

Runs the exact same MCP server (all tools) over HTTP instead of stdio, enabling:
- OpenCode, which only supports remote MCP servers
- Dockerized / remotely hosted agents
- A single centrally-hosted memory shared by a team

Usage:
    graph-memory-mcp-http                       # 127.0.0.1:8765, endpoint /mcp
    GRAPH_MEMORY_HTTP_HOST=0.0.0.0 GRAPH_MEMORY_HTTP_PORT=9000 graph-memory-mcp-http

Requires the `http` extra (uvicorn + starlette) — already satisfied when the
`mcp` SDK pulls them in; otherwise: pip install epistemic-graph-memory[http]
"""
import os


def create_http_app():
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    # Reuse the single low-level Server instance (all 17 tools) from server.py.
    from graph_memory.mcp.server import server

    # stateless=True: each request gets an independent session — safe for
    # multiple concurrent agents hitting one endpoint without session affinity.
    # `app` must be the low-level Server instance (the manager calls app.run()).
    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
    )

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    async def health(request):
        return JSONResponse({"status": "ok", "server": "graph-memory-mcp-http", "endpoint": "/mcp"})

    async def lifespan(app):
        async with session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/health", health),
            # Mounted at root so POST /mcp matches directly — a path-specific
            # Mount would 307-redirect to /mcp/ and break strict clients.
            Mount("/", app=handle_mcp),
        ],
        lifespan=lifespan,
    )


def main():
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "[!] uvicorn/starlette not installed. Run: pip install epistemic-graph-memory[http]"
        )

    host = os.environ.get("GRAPH_MEMORY_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("GRAPH_MEMORY_HTTP_PORT", "8765"))
    print(f"[*] graph-memory MCP (streamable HTTP) listening on http://{host}:{port}/mcp")
    uvicorn.run(create_http_app(), host=host, port=port)


if __name__ == "__main__":
    main()
