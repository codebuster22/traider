"""MCP endpoints supporting HTTP Streamable transport with session persistence."""
import asyncio
import json
import uuid
from starlette.requests import Request

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server


# Store active sessions - maps session_id to (transport, server_task)
_sessions: dict[str, tuple[StreamableHTTPServerTransport, asyncio.Task]] = {}


async def get_or_create_session(session_id: str | None) -> tuple[str, StreamableHTTPServerTransport]:
    """Get existing session or create a new one."""
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id in _sessions:
        transport, task = _sessions[session_id]
        # Check if task is still running
        if not task.done():
            return session_id, transport
        # Task finished, remove old session
        del _sessions[session_id]

    # Create new transport and session
    transport = StreamableHTTPServerTransport(
        mcp_session_id=session_id,
        is_json_response_enabled=True,
    )

    # Connect and start server
    streams_context = transport.connect()
    streams = await streams_context.__aenter__()
    read_stream, write_stream = streams

    server_task = asyncio.create_task(
        mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )
    )

    _sessions[session_id] = (transport, server_task)

    # Clean up session when server task completes
    def cleanup_session(task):
        if session_id in _sessions:
            del _sessions[session_id]

    server_task.add_done_callback(cleanup_session)

    return session_id, transport


async def handle_mcp_post(request: Request):
    """
    Handle MCP POST requests with HTTP Streamable transport.

    Sessions are persisted across requests using the Mcp-Session-Id header.
    """
    # Get session ID from headers
    session_id = request.headers.get("mcp-session-id")

    # Get or create session
    session_id, transport = await get_or_create_session(session_id)

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
