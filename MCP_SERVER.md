# Fabric Inventory MCP Server

This is a Model Context Protocol (MCP) server that exposes the fabric inventory service as tools that can be used by MCP clients like Claude Desktop.

## What is MCP?

Model Context Protocol (MCP) is an open protocol that enables AI assistants to securely connect to external tools and data sources. This MCP server allows Claude and other AI assistants to interact with your fabric inventory system.

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

## Configuration for MCP Clients

### Claude Desktop

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "fabric-inventory": {
      "command": "python",
      "args": ["/absolute/path/to/traider/mcp_server.py"],
      "env": {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/inventory"
      }
    }
  }
}
```

**Important**: Replace `/absolute/path/to/traider` with the actual absolute path to this project directory.

### Other MCP Clients

For other MCP clients, configure them to run:
```bash
python /path/to/traider/mcp_server.py
```

With the environment variable:
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/inventory
```

## Testing the MCP Server

You can test the server manually using the MCP Inspector:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Run with your server
DATABASE_URL=postgresql://user:pass@localhost:5432/inventory \
  mcp-inspector python mcp_server.py
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
         │ (stdio)
┌────────▼────────┐
│   MCP Server    │
│  mcp_server.py  │
└────────┬────────┘
         │
         │ Direct DB Access
         │ (same as FastAPI app)
┌────────▼────────┐
│   PostgreSQL    │
│   Database      │
└─────────────────┘
```

The MCP server uses the same repository layer (`app/repo.py`) as the FastAPI service, ensuring consistent business logic and data access patterns.

## Business Logic

- **UOM Conversion**: 1 roll = 200 meters (all stored in meters in DB)
- **Stock Movements**: Receipts add stock, issues subtract stock, adjustments can be +/-
- **Stock Balance**: Real-time calculation from movements table
- **Search**: Supports fuzzy text search using PostgreSQL trigram indexes

## Troubleshooting

### Connection Issues

If Claude Desktop can't connect to the server:

1. Check the logs (Claude Desktop → Settings → Developer → View Logs)
2. Verify the absolute path in the config is correct
3. Ensure DATABASE_URL is set correctly
4. Test database connection: `psql $DATABASE_URL`

### Database Not Initialized

The server automatically runs DDL at startup, but if you see table errors:

```bash
# Initialize manually
python -c "from app.db import init_db; init_db()"
```

### Permission Issues

Ensure the Python interpreter has access to:
- The project directory
- The PostgreSQL database
- Required Python packages

## Development

To modify the MCP server:

1. Edit `mcp_server.py`
2. Restart Claude Desktop (or reconnect your MCP client)
3. The changes will take effect immediately

## Security Notes

- This MCP server has **no authentication** - it's designed for local development
- The server connects directly to your database
- Only expose this to trusted MCP clients
- For production, consider:
  - Adding authentication to the database
  - Running with restricted database user permissions
  - Using the FastAPI service instead for API-based access with auth

## Related Files

- `mcp_server.py` - MCP server implementation
- `app/repo.py` - Repository layer (shared with FastAPI)
- `app/db.py` - Database connection (shared with FastAPI)
- `app/models.py` - Pydantic models (shared with FastAPI)

## Learn More

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Configuration](https://docs.anthropic.com/claude/docs/model-context-protocol)
