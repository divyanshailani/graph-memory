"""
Streamable-HTTP MCP transport (v3.6.0 "Open Borders").

Runs the exact same MCP server (all 19 tools) over HTTP instead of stdio, enabling:
- OpenCode, which only supports remote MCP servers
- Dockerized / remotely hosted agents
- A single centrally-hosted memory shared by a team

Usage:
    graph-memory-mcp-http                       # 127.0.0.1:8765, endpoint /mcp
    GRAPH_MEMORY_HTTP_HOST=0.0.0.0 GRAPH_MEMORY_HTTP_PORT=9000 graph-memory-mcp-http

SECURITY WARNING (v3.8.0):
    By default, this server binds to 127.0.0.1 (localhost only) and includes
    DNS rebinding protection. 
    
    If you bind to 0.0.0.0 for remote access:
    - The server exposes FULL filesystem and database access via MCP tools
    - Set GRAPH_MEMORY_API_KEY to require authentication
    - Use a reverse proxy (nginx, Caddy) with TLS and proper access controls
    - Consider network-level restrictions (VPN, firewall rules)
    
    Authentication:
    - Set GRAPH_MEMORY_API_KEY environment variable
    - Clients must include: Authorization: Bearer <API_KEY>
    - Requests without valid authentication are rejected with 401

Requires the `http` extra (uvicorn + starlette) — already satisfied when the
`mcp` SDK pulls them in; otherwise: pip install epistemic-graph-memory[http]
"""
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette import status


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple API key authentication for HTTP MCP server."""
    
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key
    
    async def dispatch(self, request, call_next):
        # Allow health checks without auth
        if request.url.path == "/health":
            return await call_next(request)
        
        # Require Bearer token for MCP endpoints
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header. Use: Authorization: Bearer <API_KEY>"},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        if token != self.api_key:
            return JSONResponse(
                {"error": "Invalid API key"},
                status_code=status.HTTP_401_UNAUTHORIZED
            )
        
        return await call_next(request)


def create_http_app():
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.responses import JSONResponse
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager, TransportSecuritySettings

    # Reuse the single low-level Server instance (all 19 tools) from server.py.
    from graph_memory.mcp.server import server

    # Security settings: DNS rebinding protection enabled by default
    # Only allow localhost hosts unless explicitly configured for remote access
    host = os.environ.get("GRAPH_MEMORY_HTTP_HOST", "127.0.0.1")
    
    # Configure allowed hosts based on binding
    if host == "127.0.0.1" or host == "localhost":
        allowed_hosts = ["localhost", "127.0.0.1"]
    else:
        # For remote access, allow any host (user should use reverse proxy for restrictions)
        allowed_hosts = None  # Allow all hosts
    
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    )

    # stateless=True: each request gets an independent session — safe for
    # multiple concurrent agents hitting one endpoint without session affinity.
    # `app` must be the low-level Server instance (the manager calls app.run()).
    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=security_settings,
    )

    async def handle_mcp(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    async def health(request):
        return JSONResponse({"status": "ok", "server": "graph-memory-mcp-http", "endpoint": "/mcp"})

    async def lifespan(app):
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/health", health),
            # Mounted at root so POST /mcp matches directly — a path-specific
            # Mount would 307-redirect to /mcp/ and break strict clients.
            Mount("/", app=handle_mcp),
        ],
        lifespan=lifespan,
    )
    
    # Add API key authentication if configured
    api_key = os.environ.get("GRAPH_MEMORY_API_KEY")
    if api_key:
        app = APIKeyMiddleware(app, api_key)
    
    return app


def main():
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "[!] uvicorn/starlette not installed. Run: pip install epistemic-graph-memory[http]"
        )

    host = os.environ.get("GRAPH_MEMORY_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("GRAPH_MEMORY_HTTP_PORT", "8765"))
    api_key = os.environ.get("GRAPH_MEMORY_API_KEY")
    
    # Security warning for remote binding
    if host == "0.0.0.0":
        print("[!] SECURITY WARNING: Binding to 0.0.0.0 exposes this server to the network!")
        if not api_key:
            print("[!] WARNING: No API key set. Set GRAPH_MEMORY_API_KEY for authentication.")
        print("[!] Consider using a reverse proxy with TLS and access controls.")
    
    auth_status = "enabled" if api_key else "disabled"
    print(f"[*] graph-memory MCP (streamable HTTP) listening on http://{host}:{port}/mcp")
    print(f"[*] Authentication: {auth_status}")
    uvicorn.run(create_http_app(), host=host, port=port)


if __name__ == "__main__":
    main()
