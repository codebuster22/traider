"""MCP SSE endpoint for HTTP-based MCP connections."""
import asyncio
import json
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from sse_starlette import EventSourceResponse

from app.mcp import mcp_server


router = APIRouter(prefix="/mcp", tags=["mcp"])


# Store active sessions
_sessions = {}


@router.get("/sse")
async def handle_sse(request: Request):
    """
    SSE endpoint for MCP connections.

    This endpoint allows MCP clients (like Claude Desktop) to connect via HTTP/SSE
    instead of using stdio transport.

    Usage in Claude Desktop config:
    {
      "mcpServers": {
        "fabric-inventory": {
          "url": "http://localhost:8000/mcp/sse"
        }
      }
    }
    """
    session_id = id(request)

    # Create message queues for this session
    read_queue = asyncio.Queue()
    write_queue = asyncio.Queue()
    _sessions[session_id] = {"read": read_queue, "write": write_queue}

    async def read_stream():
        """Read messages from the client."""
        while True:
            message = await read_queue.get()
            if message is None:  # Shutdown signal
                break
            yield message

    async def write_stream(message):
        """Write messages to the client."""
        await write_queue.put(message)

    # Start MCP server in background
    async def run_server():
        try:
            async with mcp_server.run(
                read_stream(),
                write_stream,
                mcp_server.create_initialization_options()
            ):
                await request.is_disconnected()
        finally:
            if session_id in _sessions:
                del _sessions[session_id]

    asyncio.create_task(run_server())

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from the write queue."""
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Wait for messages from the server with timeout
                    message = await asyncio.wait_for(write_queue.get(), timeout=1.0)
                    yield json.dumps(message)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield json.dumps({"type": "keepalive"})

        finally:
            # Signal shutdown to read stream
            await read_queue.put(None)

    return EventSourceResponse(event_generator())


@router.post("/message")
async def handle_message(request: Request):
    """
    Handle incoming MCP messages from the client.

    This endpoint receives messages from the MCP client and forwards them
    to the appropriate session's read queue.
    """
    session_id = request.headers.get("X-Session-ID")
    if not session_id or int(session_id) not in _sessions:
        return {"error": "Invalid or missing session ID"}, 400

    message = await request.json()
    session = _sessions[int(session_id)]
    await session["read"].put(message)

    return {"status": "ok"}
