# Fabric Inventory MCP Server

This is a Model Context Protocol (MCP) server that exposes the fabric inventory service as tools that can be used by MCP clients like Claude Desktop.

## What is MCP?

Model Context Protocol (MCP) is an open protocol that enables AI assistants to securely connect to external tools and data sources. This MCP server allows Claude and other AI assistants to interact with your fabric inventory system.

## Transport Method

The MCP server is integrated into the FastAPI application and uses **Server-Sent Events (SSE)** over HTTP/HTTPS. This means you simply add a URL to your MCP client configuration instead of running a separate process.

## Available Tools

The MCP server exposes the following tools:

### Master Data Tools

1. **create_fabric** - Create a new fabric
   - `fabric_code` (string): Unique fabric code
   - `name` (string): Fabric name
   - `image_url` (string, optional): Image URL

2. **search_fabrics** - Search fabrics with filters
   - `q` (string, optional): Free text search
   - `fabric_code` (string, optional): Filter by code
   - `name` (string, optional): Filter by name
   - `limit` (int): Max results (default: 20)
   - `offset` (int): Skip results (default: 0)

3. **create_variant** - Create a new fabric variant
   - `fabric_id` (int): Parent fabric ID
   - `color_code` (string): Color code
   - `gsm` (int): Grams per square meter
   - `width` (int): Width in inches
   - `finish` (string): Finish type
   - `image_url` (string, optional): Image URL

4. **get_variant** - Get variant details by ID
   - `variant_id` (int): Variant ID

5. **search_variants** - Search variants with filters
   - `q` (string, optional): Free text search
   - `fabric_id` (int, optional): Filter by fabric ID
   - `fabric_code` (string, optional): Filter by fabric code
   - `color_code` (string, optional): Filter by color code
   - `gsm` (int, optional): Exact GSM
   - `gsm_min` (int, optional): Minimum GSM
   - `gsm_max` (int, optional): Maximum GSM
   - `include_stock` (bool): Include stock info (default: false)
   - `in_stock_only` (bool): Only variants with stock (default: false)
   - `limit` (int): Max results (default: 20)
   - `offset` (int): Skip results (default: 0)

### Stock Movement Tools

6. **receive_stock** - Record stock receipt (increases inventory)
   - `variant_id` (int): Variant ID
   - `qty` (float): Quantity to receive
   - `uom` (string): Unit ("m" or "roll")
   - `reason` (string, optional): Free-text reason

7. **issue_stock** - Record stock issue/consumption (decreases inventory)
   - `variant_id` (int): Variant ID
   - `qty` (float): Quantity to issue
   - `uom` (string): Unit ("m" or "roll")
   - `reason` (string, optional): Free-text reason

8. **adjust_stock** - Record stock adjustment (can be +/-)
   - `variant_id` (int): Variant ID
   - `qty` (float): Adjustment quantity
   - `uom` (string): Unit ("m" or "roll")
   - `reason` (string, optional): Free-text reason

### Stock Query Tools

9. **get_stock** - Get current stock balance for a variant
   - `variant_id` (int): Variant ID
   - `uom` (string): Display unit ("m" or "roll", default: "m")

10. **get_stock_batch** - Get stock for multiple variants
    - `variant_ids` (list[int]): List of variant IDs
    - `uom` (string): Display unit ("m" or "roll", default: "m")

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your database:
```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/inventory
```

3. Start the FastAPI service:
```bash
./run.sh
```

The MCP server will be available at: `http://localhost:8000/mcp/sse`

## Configuration for MCP Clients

### Claude Desktop

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "fabric-inventory": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

**For Production (HTTPS)**:
```json
{
  "mcpServers": {
    "fabric-inventory": {
      "url": "https://your-domain.com/mcp/sse"
    }
  }
}
```

### Other MCP Clients

For other MCP clients, configure them to connect to:
```
http://localhost:8000/mcp/sse
```

Or in production:
```
https://your-domain.com/mcp/sse
```

## Testing the MCP Server

### Quick Test

1. Start the FastAPI service:
```bash
./run.sh
```

2. Verify the MCP endpoint is accessible:
```bash
curl http://localhost:8000/mcp/sse
```

You should see an SSE connection established.

### Using MCP Inspector

For interactive testing with the MCP Inspector:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Test the HTTP endpoint
mcp-inspector http://localhost:8000/mcp/sse
```

## Usage Examples with Claude Desktop

Once configured, you can interact with Claude using natural language:

**Example 1: Create a fabric**
> "Create a new fabric with code FAB-001 and name Cotton Jersey"

**Example 2: Search fabrics**
> "Search for all fabrics with 'cotton' in the name"

**Example 3: Create variant and add stock**
> "Create a variant for fabric ID 1 with color code BLK-9001, GSM 180, width 72, and finish Bio. Then receive 5 rolls of stock."

**Example 4: Check inventory**
> "What's the current stock balance for variant 1 in rolls?"

**Example 5: Search variants with stock**
> "Show me all variants that are currently in stock with their quantities"

## Architecture

```
┌─────────────────┐
│   MCP Client    │
│ (Claude Desktop)│
└────────┬────────┘
         │ MCP Protocol
         │ (HTTP/SSE)
         │
┌────────▼────────────────────────┐
│      FastAPI Application        │
│                                 │
│  ┌──────────┐    ┌──────────┐  │
│  │ REST API │    │ MCP /mcp │  │
│  │ Routes   │    │ /sse     │  │
│  └────┬─────┘    └────┬─────┘  │
│       │               │         │
│       └───────┬───────┘         │
│           ┌───▼────┐            │
│           │ repo.py│            │
│           │  (DB)  │            │
│           └───┬────┘            │
└───────────────┼─────────────────┘
                │
         ┌──────▼──────┐
         │ PostgreSQL  │
         │  Database   │
         └─────────────┘
```

The MCP endpoint is integrated into the FastAPI application and uses the same repository layer (`app/repo.py`) as the REST API, ensuring consistent business logic and data access patterns.

## Business Logic

- **UOM Conversion**: 1 roll = 200 meters (all stored in meters in DB)
- **Stock Movements**: Receipts add stock, issues subtract stock, adjustments can be +/-
- **Stock Balance**: Real-time calculation from movements table
- **Search**: Supports fuzzy text search using PostgreSQL trigram indexes

## Troubleshooting

### Connection Issues

If Claude Desktop can't connect to the MCP server:

1. **Verify the service is running**:
   ```bash
   curl http://localhost:8000/
   # Should return: {"status":"ok","service":"fabric-inventory"}
   ```

2. **Check the MCP endpoint**:
   ```bash
   curl http://localhost:8000/mcp/sse
   # Should establish an SSE connection
   ```

3. **Review logs** (Claude Desktop → Settings → Developer → View Logs)

4. **Ensure DATABASE_URL is set**:
   ```bash
   echo $DATABASE_URL
   ```

5. **Test database connection**:
   ```bash
   psql $DATABASE_URL
   ```

### Database Not Initialized

The FastAPI service automatically runs DDL at startup. If you see table errors:

```bash
# Initialize manually
python -c "from app.db import init_db; init_db()"
```

### CORS Issues (Production)

If connecting from a different domain, you may need to enable CORS in `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai"],  # Add your client origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Development

To modify the MCP server:

1. Edit `src/traider/mcp.py` (tool definitions) or `src/traider/routes/mcp.py` (HTTP endpoint)
2. Restart the FastAPI service (`./run.sh` or `uv run traider-server`)
3. Reconnect your MCP client (or restart Claude Desktop)
4. Changes will take effect immediately

### Adding New Tools

1. Define input schema in `src/traider/mcp.py`
2. Add tool to `list_tools()` handler
3. Implement tool logic in `call_tool()` handler
4. Use existing `src/traider/repo.py` functions for database operations

## Security Notes

- This MCP server has **no authentication** by default
- Suitable for local development and trusted environments
- For production deployments:
  - Use HTTPS (not HTTP)
  - Add authentication middleware
  - Implement rate limiting
  - Use restricted database user permissions
  - Enable CORS only for trusted origins
  - Consider API keys or OAuth for MCP access

## Related Files

- `src/traider/mcp.py` - MCP tool definitions and handlers
- `src/traider/routes/mcp.py` - SSE endpoint for HTTP/MCP transport
- `src/traider/repo.py` - Repository layer (shared with REST API)
- `src/traider/db.py` - Database connection (shared with REST API)
- `src/traider/models.py` - Pydantic models (shared with REST API)
- `pyproject.toml` - Project configuration and dependencies

## Learn More

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Configuration](https://docs.anthropic.com/claude/docs/model-context-protocol)
