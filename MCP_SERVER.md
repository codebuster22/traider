# Fabric Inventory MCP Server

This is a Model Context Protocol (MCP) server that exposes the fabric inventory service as tools that can be used by MCP clients like Claude Desktop.

## What is MCP?

Model Context Protocol (MCP) is an open protocol that enables AI assistants to securely connect to external tools and data sources. This MCP server allows Claude and other AI assistants to interact with your fabric inventory system.

## Transport Method

The MCP server is integrated into the FastAPI application and uses **HTTP Streamable Transport** - the current MCP standard. This means you simply add a URL to your MCP client configuration instead of running a separate process.

## Authentication

**No authentication is required.** The MCP server is configured with:
- CORS enabled for all origins (`*`)
- No API keys or tokens needed
- Simply connect using the endpoint URL

For production, you may want to add authentication middleware.

## Available Tools

The MCP server exposes **22 tools** organized by category. All tools use business identifiers (fabric_code, color_code) rather than internal IDs.

### Image Upload Tools

1. **upload_image** - Upload an image to Cloudinary
   - `image_data` (string): Base64 encoded image data
   - `filename` (string, optional): Filename without extension
   - `folder` (string): Cloudinary folder path (default: "traider")

### Fabric Management Tools

2. **create_fabric** - Create a new fabric with optional aliases
   - `fabric_code` (string): Unique fabric code (e.g., 'FAB-001')
   - `name` (string): Fabric name
   - `image_url` (string, optional): Image URL if already uploaded
   - `image_data` (string, optional): Base64 image data to upload
   - `gallery` (dict, optional): Gallery with photoshoot namespaces
   - `aliases` (list[string], optional): Alternative names for the fabric

3. **update_fabric** - Update an existing fabric
   - `fabric_code` (string): Fabric code to update
   - `name` (string, optional): New fabric name
   - `image_url` (string, optional): New image URL
   - `image_data` (string, optional): Base64 image data to upload
   - `gallery` (dict, optional): New gallery data

4. **get_fabric** - Get a fabric by its fabric_code
   - `fabric_code` (string): Fabric code to retrieve

5. **search_fabrics** - Search fabrics with filters and pagination
   - `q` (string, optional): Free text search across fabric_code, name, and aliases
   - `fabric_code` (string, optional): Filter by fabric code (partial match)
   - `name` (string, optional): Filter by name (partial match)
   - `limit` (int): Max results (default: 20, max: 100)
   - `offset` (int): Skip results (default: 0)

### Alias Management Tools

6. **add_alias** - Add an alternative name to a fabric
   - `fabric_code` (string): Fabric code to add alias to
   - `alias` (string): Alias to add

7. **remove_alias** - Remove an alias from a fabric
   - `fabric_code` (string): Fabric code to remove alias from
   - `alias` (string): Alias to remove

8. **get_aliases** - Get all aliases for a fabric
   - `fabric_code` (string): Fabric code to get aliases for

### Variant Management Tools

9. **create_variant** - Create a new fabric variant
   - `fabric_code` (string): Fabric code of the parent fabric
   - `color_code` (string): Color code (e.g., 'BLK-9001')
   - `finish` (string): Finish type (default: "Standard")
   - `gsm` (int, optional): Grams per square meter
   - `width` (int, optional): Width in inches
   - `image_url` (string, optional): Image URL
   - `image_data` (string, optional): Base64 image data to upload
   - `gallery` (dict, optional): Gallery with photoshoot namespaces

10. **update_variant** - Update an existing variant
    - `fabric_code` (string): Fabric code of the variant
    - `color_code` (string): Color code to update
    - `new_color_code` (string, optional): New color code if renaming
    - `gsm` (int, optional): New GSM value
    - `width` (int, optional): New width in inches
    - `finish` (string, optional): New finish type
    - `image_url` (string, optional): New image URL
    - `image_data` (string, optional): Base64 image data to upload
    - `gallery` (dict, optional): New gallery data

11. **get_variant** - Get variant details
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code

12. **delete_variant** - Delete a variant
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code to delete

13. **search_variants** - Search variants with filters, stock info, and pagination
    - `q` (string, optional): Free text search
    - `fabric_code` (string, optional): Filter by fabric code
    - `color_code` (string, optional): Filter by color code
    - `gsm` (int, optional): Exact GSM filter
    - `gsm_min` (int, optional): Minimum GSM
    - `gsm_max` (int, optional): Maximum GSM
    - `width` (int, optional): Exact width filter
    - `width_min` (int, optional): Minimum width
    - `width_max` (int, optional): Maximum width
    - `finish` (string, optional): Filter by finish type (partial match)
    - `include_stock` (bool): Include stock information (default: false)
    - `in_stock_only` (bool): Only variants with stock > 0 (default: false)
    - `limit` (int): Max results (default: 20, max: 100)
    - `offset` (int): Skip results (default: 0)
    - `sort_by` (string): Sort field: id, fabric_code, color_code, gsm, width (default: "color_code")
    - `sort_dir` (string): Sort direction: asc or desc (default: "asc")

### Stock Movement Tools

14. **receive_stock** - Record stock receipt (increases inventory)
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code
    - `qty` (float): Quantity in meters
    - `uom` (string): Unit of measure (default: "m")
    - `roll_count` (int, optional): Number of rolls
    - `document_id` (string, optional): Invoice/receipt ID
    - `reason` (string, optional): Free-text reason

15. **issue_stock** - Record stock issue (decreases inventory)
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code
    - `qty` (float): Quantity in meters (automatically negated)
    - `uom` (string): Unit of measure (default: "m")
    - `roll_count` (int, optional): Number of rolls
    - `document_id` (string, optional): Invoice/receipt ID
    - `reason` (string, optional): Free-text reason

16. **adjust_stock** - Record stock adjustment (can be +/-)
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code
    - `qty` (float): Adjustment quantity (positive or negative)
    - `uom` (string): Unit of measure (default: "m")
    - `roll_count` (int, optional): Number of rolls
    - `document_id` (string, optional): Invoice/receipt ID
    - `reason` (string, optional): Free-text reason

### Stock Query Tools

17. **get_stock** - Get current stock balance
    - `fabric_code` (string): Fabric code
    - `color_code` (string): Color code
    - `uom` (string): Display unit ("m" or "roll", default: "m")

### Search Tools

18. **unified_search** - Search across fabrics and variants in one call
    - `q` (string): Search query
    - `include_fabrics` (bool): Include fabrics (default: true)
    - `include_variants` (bool): Include variants (default: true)
    - `include_stock` (bool): Include stock info for variants (default: false)
    - `limit` (int): Max results per category (default: 20, max: 100)

### Batch Operations

19. **create_variants_batch** - Create multiple variants at once (max 100)
    - `fabric_code` (string): Fabric code to create variants under
    - `variants` (list): List of variant objects with color_code, finish, gsm, width

20. **receive_stock_batch** - Record stock inflow for multiple variants (max 50)
    - `items` (list): List of items with fabric_code, color_code, qty, uom, roll_count
    - `document_id` (string, optional): Document/invoice ID
    - `reason` (string, optional): Reason for receipt

21. **issue_stock_batch** - Record stock outflow for multiple variants (max 50)
    - `items` (list): List of items with fabric_code, color_code, qty, uom, roll_count
    - `document_id` (string, optional): Document/invoice ID
    - `customer_name` (string, optional): Customer name
    - `reason` (string, optional): Reason for issue

22. **search_variants_batch** - Search multiple variants by color codes
    - `fabric_code` (string): Fabric code to search within
    - `color_codes` (list[string]): List of color codes to find
    - `include_stock` (bool): Include stock balances (default: false)

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

The MCP server will be available at: `http://localhost:8000/mcp`

## Configuration for MCP Clients

### Claude Desktop

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "fabric-inventory": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**For Production (HTTPS)**:
```json
{
  "mcpServers": {
    "fabric-inventory": {
      "url": "https://your-domain.com/mcp"
    }
  }
}
```

### Other MCP Clients

For other MCP clients, configure them to connect to:
```
http://localhost:8000/mcp
```

Or in production:
```
https://your-domain.com/mcp
```

## Testing the MCP Server

### Quick Test

1. Start the FastAPI service:
```bash
./run.sh
```

2. Verify the MCP endpoint is accessible:
```bash
curl http://localhost:8000/mcp
```

You should see server info including protocol and transport type.

### Using MCP Inspector

For interactive testing with the MCP Inspector:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Test the HTTP endpoint
mcp-inspector http://localhost:8000/mcp
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
         │ (HTTP Streamable)
         │
┌────────▼────────────────────────┐
│      FastAPI Application        │
│         (CORS: all origins)     │
│                                 │
│  ┌──────────┐    ┌──────────┐  │
│  │ REST API │    │ MCP /mcp │  │
│  │ Routes   │    │ endpoint │  │
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
   curl http://localhost:8000/mcp
   # Should return server info JSON
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

### CORS Issues

CORS is already enabled for all origins (`*`) by default. If you need to restrict origins for production:

```python
# In src/traider/main.py, modify the CORS middleware:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai", "https://your-app.com"],  # Restrict to specific origins
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
- CORS is enabled for **all origins** (`*`)
- Suitable for local development, trusted environments, and public MCP services
- For production deployments with restricted access:
  - Use HTTPS (not HTTP)
  - Add authentication middleware (API keys, OAuth, etc.)
  - Implement rate limiting
  - Use restricted database user permissions
  - Restrict CORS to specific trusted origins

## Related Files

- `src/traider/mcp.py` - MCP tool definitions and handlers
- `src/traider/routes/mcp.py` - HTTP Streamable endpoint for MCP transport
- `src/traider/main.py` - FastAPI app with CORS configuration
- `src/traider/repo.py` - Repository layer (shared with REST API)
- `src/traider/db.py` - Database connection (shared with REST API)
- `src/traider/models.py` - Pydantic models (shared with REST API)
- `pyproject.toml` - Project configuration and dependencies

## Learn More

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Desktop MCP Configuration](https://docs.anthropic.com/claude/docs/model-context-protocol)
