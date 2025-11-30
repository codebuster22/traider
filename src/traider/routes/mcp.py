"""MCP HTTP Streamable transport with proper lifespan management."""
import asyncio
import json
import logging
from typing import Optional

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server

logger = logging.getLogger(__name__)


# Global state - initialized in lifespan
_transport: Optional[StreamableHTTPServerTransport] = None
_server_task: Optional[asyncio.Task] = None


async def startup_mcp():
    """Initialize MCP transport and server. Called from lifespan startup."""
    global _transport, _server_task

    _transport = StreamableHTTPServerTransport(
        mcp_session_id=None,  # Let transport manage session IDs
        is_json_response_enabled=True,
    )

    # Enter the connect context - this starts the message router
    # We store the context manager so we can exit it later
    _transport._connect_cm = _transport.connect()
    streams = await _transport._connect_cm.__aenter__()
    read_stream, write_stream = streams

    # Start MCP server as background task
    _server_task = asyncio.create_task(
        mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )
    )

    logger.info("MCP server started")


async def shutdown_mcp():
    """Shutdown MCP transport and server. Called from lifespan shutdown."""
    global _transport, _server_task

    if _server_task:
        _server_task.cancel()
        try:
            await _server_task
        except asyncio.CancelledError:
            pass
        _server_task = None

    if _transport and hasattr(_transport, '_connect_cm'):
        try:
            await _transport._connect_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing MCP transport: {e}")
        _transport = None

    logger.info("MCP server stopped")


async def mcp_post_asgi(scope, receive, send):
    """Handle MCP POST requests."""
    global _transport

    if _transport is None:
        body = b'{"error": "MCP server not initialized"}'
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"access-control-allow-origin", b"*"],
            ],
        })
        await send({"type": "http.response.body", "body": body})
        return

    try:
        await _transport.handle_request(scope, receive, send)
    except Exception as e:
        logger.exception("Error handling MCP request")
        body = json.dumps({"error": str(e)}).encode()
        try:
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                    [b"access-control-allow-origin", b"*"],
                ],
            })
            await send({"type": "http.response.body", "body": body})
        except Exception:
            pass  # Response may have already started


async def mcp_get_asgi(scope, receive, send):
    """Handle MCP GET requests - returns server info."""
    info = {
        "name": "fabric-inventory",
        "version": "1.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "auth": "none",
        "status": "running" if _transport else "not initialized",
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
    await send({"type": "http.response.body", "body": body})


class MCPApp:
    """Pure ASGI application for MCP endpoint."""

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
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": self.CORS_HEADERS,
            })
            await send({"type": "http.response.body", "body": b""})
        elif method == "POST":
            await mcp_post_asgi(scope, receive, send)
        elif method == "GET":
            await mcp_get_asgi(scope, receive, send)
        else:
            body = b'{"error": "Method not allowed"}'
            await send({
                "type": "http.response.start",
                "status": 405,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ] + self.CORS_HEADERS,
            })
            await send({"type": "http.response.body", "body": body})


mcp_asgi_app = MCPApp()
