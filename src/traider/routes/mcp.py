"""MCP endpoints supporting HTTP Streamable transport."""
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import APIRouter

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server


router = APIRouter(tags=["mcp"])


# ============================================================================
# HTTP Streamable Transport
# ============================================================================

@asynccontextmanager
async def create_streamable_transport(session_id: str | None):
    """Create HTTP Streamable transport and run the MCP server."""
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


async def handle_mcp_post(scope, receive, send):
    """Handle MCP POST requests with HTTP Streamable transport."""
    headers = dict(scope.get("headers", []))
    session_id = headers.get(b"mcp-session-id", b"").decode() or None

    async with create_streamable_transport(session_id) as transport:
        await transport.handle_request(scope, receive, send)


async def handle_mcp_get(scope, receive, send):
    """Handle MCP GET requests - return server info."""
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
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


async def mcp_asgi_app(scope, receive, send):
    """
    Pure ASGI app for MCP endpoint.

    Handles:
    - GET /mcp - Returns server info
    - POST /mcp - HTTP Streamable MCP protocol
    """
    if scope["type"] != "http":
        return

    method = scope.get("method", "GET")

    if method == "GET":
        await handle_mcp_get(scope, receive, send)
    elif method == "POST":
        await handle_mcp_post(scope, receive, send)
    else:
        # Method not allowed
        body = b'{"error": "Method not allowed"}'
        await send({
            "type": "http.response.start",
            "status": 405,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
