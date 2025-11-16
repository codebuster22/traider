"""MCP SSE endpoint for HTTP-based MCP connections."""
from fastapi import APIRouter, Request
from fastapi.responses import Response
from mcp.server.sse import SseServerTransport

from traider.mcp import mcp_server


router = APIRouter(prefix="/mcp", tags=["mcp"])

# Create SSE transport with the message endpoint path
# This path is sent to clients, so it must be the full path they should POST to
sse_transport = SseServerTransport("/mcp/messages")


@router.get("/sse")
async def handle_sse(request: Request):
    """
    SSE endpoint for MCP connections.

    This endpoint allows MCP clients (like Claude Desktop) to connect via HTTP/SSE
    instead of using stdio transport.

    Usage in Claude Desktop/Claude Code config:
    {
      "mcpServers": {
        "fabric-inventory": {
          "url": "https://your-domain.com/mcp/sse"
        }
      }
    }
    """
    async with sse_transport.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )


@router.post("/messages")
async def handle_post_message(request: Request):
    """Handle POST messages from MCP client."""
    await sse_transport.handle_post_message(
        request.scope,
        request.receive,
        request._send
    )
