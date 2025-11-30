"""MCP endpoints supporting HTTP Streamable transport."""
import asyncio
import json
from contextlib import asynccontextmanager
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server


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


async def handle_mcp_post(request: Request):
    """
    Handle MCP POST requests with HTTP Streamable transport.

    This is a Starlette endpoint that extracts ASGI primitives from the Request
    and passes them to the MCP transport, which handles its own response.
    """
    # Get session ID from headers
    session_id = request.headers.get("mcp-session-id")

    async with create_streamable_transport(session_id) as transport:
        # Pass ASGI primitives to the transport - it handles its own response
        await transport.handle_request(request.scope, request.receive, request._send)


async def handle_mcp_get(request: Request):
    """
    Handle MCP GET requests - return server info.

    This endpoint provides discovery information about the MCP server.
    """
    info = {
        "name": "fabric-inventory",
        "version": "1.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "auth": "none",
        "documentation": "POST JSON-RPC messages to this endpoint. No authentication required."
    }

    # Use raw ASGI to send response (consistent with POST handler)
    body = json.dumps(info).encode("utf-8")

    await request._send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body)).encode()],
        ],
    })
    await request._send({
        "type": "http.response.body",
        "body": body,
    })
