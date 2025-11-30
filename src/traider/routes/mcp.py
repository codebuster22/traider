"""MCP endpoints supporting HTTP Streamable transport."""
import asyncio
import json
from contextlib import asynccontextmanager

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server


# ============================================================================
# HTTP Streamable Transport - Pure ASGI handlers
# ============================================================================

@asynccontextmanager
async def create_transport_session(session_id: str | None):
    """Create transport and run MCP server for a single request."""
    transport = StreamableHTTPServerTransport(
        mcp_session_id=session_id,
        is_json_response_enabled=True,
    )

    async with transport.connect() as streams:
        read_stream, write_stream = streams

        server_task = asyncio.create_task(
            mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options()
            )
        )

        try:
            yield transport
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


async def mcp_post_asgi(scope, receive, send):
    """Pure ASGI handler for MCP POST requests."""
    # Get session ID from headers
    headers = dict(scope.get("headers", []))
    session_id = headers.get(b"mcp-session-id", b"").decode() or None

    async with create_transport_session(session_id) as transport:
        await transport.handle_request(scope, receive, send)


async def mcp_get_asgi(scope, receive, send):
    """Pure ASGI handler for MCP GET requests - returns server info."""
    info = {
        "name": "fabric-inventory",
        "version": "1.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "auth": "none",
        "documentation": "POST JSON-RPC messages to this endpoint. No authentication required."
    }

    body = json.dumps(info).encode("utf-8")

    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body)).encode()],
            [b"access-control-allow-origin", b"*"],
            [b"access-control-allow-methods", b"GET, POST, OPTIONS"],
            [b"access-control-allow-headers", b"*"],
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


class MCPApp:
    """
    Pure ASGI application for MCP endpoint.

    This handles GET (info), POST (protocol), and OPTIONS (CORS preflight) requests
    without going through Starlette's request/response handling.
    """

    CORS_HEADERS = [
        [b"access-control-allow-origin", b"*"],
        [b"access-control-allow-methods", b"GET, POST, OPTIONS"],
        [b"access-control-allow-headers", b"*"],
        [b"access-control-max-age", b"86400"],
    ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return

        method = scope.get("method", "GET")

        if method == "OPTIONS":
            # CORS preflight
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": self.CORS_HEADERS,
            })
            await send({
                "type": "http.response.body",
                "body": b"",
            })
        elif method == "POST":
            await mcp_post_asgi(scope, receive, send)
        elif method == "GET":
            await mcp_get_asgi(scope, receive, send)
        else:
            # Method not allowed
            body = b'{"error": "Method not allowed"}'
            await send({
                "type": "http.response.start",
                "status": 405,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ] + self.CORS_HEADERS,
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })


# Export the ASGI app instance
mcp_asgi_app = MCPApp()
