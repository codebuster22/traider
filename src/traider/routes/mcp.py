"""MCP HTTP Streamable endpoint for HTTP-based MCP connections."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import APIRouter

from mcp.server.streamable_http import StreamableHTTPServerTransport

from traider.mcp import mcp_server


router = APIRouter(tags=["mcp"])


@asynccontextmanager
async def create_transport_and_run(session_id: str | None):
    """Create a transport, connect it, and run the MCP server."""
    transport = StreamableHTTPServerTransport(
        mcp_session_id=session_id,
        is_json_response_enabled=True,
    )

    async with transport.connect() as streams:
        read_stream, write_stream = streams

        # Start server task in the background
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
    # Get session ID from headers
    headers = dict(scope.get("headers", []))
    session_id = headers.get(b"mcp-session-id", b"").decode() or None

    async with create_transport_and_run(session_id) as transport:
        await transport.handle_request(scope, receive, send)


@router.get("/mcp")
async def mcp_get_info():
    """
    GET endpoint returns server info and available methods.

    This is useful for discovery and health checks.

    Usage in Claude Desktop/Claude Code config:
    {
      "mcpServers": {
        "fabric-inventory": {
          "url": "https://your-domain.com/mcp"
        }
      }
    }
    """
    return {
        "name": "fabric-inventory",
        "version": "1.0.0",
        "protocol": "mcp",
        "transport": "streamable-http",
        "endpoints": {
            "mcp": "POST /mcp"
        },
        "auth": "none",
        "documentation": "POST JSON-RPC messages to /mcp endpoint. No authentication required."
    }
