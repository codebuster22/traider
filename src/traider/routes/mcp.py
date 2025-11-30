"""MCP endpoints supporting HTTP Streamable transport with session persistence."""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server

logger = logging.getLogger(__name__)


@dataclass
class MCPSession:
    """Holds an active MCP session."""
    transport: StreamableHTTPServerTransport
    server_task: asyncio.Task
    read_stream: any
    write_stream: any


# Global session storage
_sessions: dict[str, MCPSession] = {}
_session_lock = asyncio.Lock()


async def get_or_create_session(session_id: Optional[str]) -> tuple[str, MCPSession]:
    """Get an existing session or create a new one."""
    async with _session_lock:
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())

        # Check for existing valid session
        if session_id in _sessions:
            session = _sessions[session_id]
            if not session.server_task.done():
                return session_id, session
            # Clean up dead session
            del _sessions[session_id]

        # Create new session
        transport = StreamableHTTPServerTransport(
            mcp_session_id=session_id,
            is_json_response_enabled=True,
        )

        # Manually enter the connect context
        connect_gen = transport.connect()
        streams = await connect_gen.__aenter__()
        read_stream, write_stream = streams

        # Start MCP server
        server_task = asyncio.create_task(
            mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options()
            )
        )

        session = MCPSession(
            transport=transport,
            server_task=server_task,
            read_stream=read_stream,
            write_stream=write_stream,
        )
        _sessions[session_id] = session

        # Schedule cleanup when server task ends
        def cleanup(task):
            asyncio.create_task(_cleanup_session(session_id))

        server_task.add_done_callback(cleanup)

        return session_id, session


async def _cleanup_session(session_id: str):
    """Clean up a session."""
    async with _session_lock:
        if session_id in _sessions:
            session = _sessions.pop(session_id)
            if not session.server_task.done():
                session.server_task.cancel()
                try:
                    await session.server_task
                except asyncio.CancelledError:
                    pass


async def mcp_post_asgi(scope, receive, send):
    """Handle MCP POST requests with session persistence."""
    # Get session ID from headers
    headers = dict(scope.get("headers", []))
    session_id = headers.get(b"mcp-session-id", b"").decode() or None

    try:
        session_id, session = await get_or_create_session(session_id)
        await session.transport.handle_request(scope, receive, send)
    except Exception as e:
        logger.exception("Error handling MCP request")
        body = json.dumps({"error": str(e)}).encode()
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"access-control-allow-origin", b"*"],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


async def mcp_get_asgi(scope, receive, send):
    """Handle MCP GET requests - returns server info."""
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
    Pure ASGI application for MCP endpoint with session persistence.

    Sessions are maintained across requests using the Mcp-Session-Id header.
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
