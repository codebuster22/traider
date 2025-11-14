"""MCP Server for Fabric Inventory Service.

This MCP server exposes the fabric inventory operations as tools
that can be used by MCP clients like Claude Desktop.
"""
import asyncio
import os
from typing import Any, Optional
from decimal import Decimal

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

# Import our existing repository functions
from app.db import init_db, close_db
from app import repo


# Initialize MCP server
mcp_server = Server("fabric-inventory")


# Tool input schemas using Pydantic
class CreateFabricInput(BaseModel):
    fabric_code: str = Field(description="Unique fabric code (e.g., 'FAB-001')")
    name: str = Field(description="Fabric name (e.g., 'Cotton Jersey')")
    image_url: Optional[str] = Field(None, description="Optional image URL")


class SearchFabricsInput(BaseModel):
    q: Optional[str] = Field(None, description="Free text search across fabric_code and name")
    fabric_code: Optional[str] = Field(None, description="Filter by fabric code (partial match)")
    name: Optional[str] = Field(None, description="Filter by name (partial match)")
    limit: int = Field(20, description="Max results to return (1-100)")
    offset: int = Field(0, description="Number of results to skip")


class CreateVariantInput(BaseModel):
    fabric_id: int = Field(description="ID of the parent fabric")
    color_code: str = Field(description="Color code (e.g., 'BLK-9001')")
    gsm: int = Field(description="Grams per square meter")
    width: int = Field(description="Width in inches")
    finish: str = Field(description="Finish type (e.g., 'Bio', 'Enzyme')")
    image_url: Optional[str] = Field(None, description="Optional image URL")


class GetVariantInput(BaseModel):
    variant_id: int = Field(description="Variant ID to retrieve")


class SearchVariantsInput(BaseModel):
    q: Optional[str] = Field(None, description="Free text search")
    fabric_id: Optional[int] = Field(None, description="Filter by fabric ID")
    fabric_code: Optional[str] = Field(None, description="Filter by fabric code")
    color_code: Optional[str] = Field(None, description="Filter by color code")
    gsm: Optional[int] = Field(None, description="Filter by exact GSM")
    gsm_min: Optional[int] = Field(None, description="Minimum GSM")
    gsm_max: Optional[int] = Field(None, description="Maximum GSM")
    include_stock: bool = Field(False, description="Include stock information")
    in_stock_only: bool = Field(False, description="Only return variants with stock > 0")
    limit: int = Field(20, description="Max results to return (1-100)")
    offset: int = Field(0, description="Number of results to skip")


class MovementInput(BaseModel):
    variant_id: int = Field(description="Variant ID to move stock for")
    qty: float = Field(description="Quantity to move")
    uom: str = Field(description="Unit of measure: 'm' (meters) or 'roll'")
    reason: Optional[str] = Field(None, description="Free-text reason for the movement")


class GetStockInput(BaseModel):
    variant_id: int = Field(description="Variant ID to get stock for")
    uom: str = Field("m", description="Unit of measure for display: 'm' or 'roll'")


class GetStockBatchInput(BaseModel):
    variant_ids: list[int] = Field(description="List of variant IDs to get stock for")
    uom: str = Field("m", description="Unit of measure for display: 'm' or 'roll'")


# Helper to convert Decimal to float for JSON serialization
def serialize_result(result: Any) -> Any:
    """Convert database results with Decimals to JSON-serializable format."""
    if isinstance(result, dict):
        return {k: serialize_result(v) for k, v in result.items()}
    elif isinstance(result, list):
        return [serialize_result(item) for item in result]
    elif isinstance(result, Decimal):
        return float(result)
    elif hasattr(result, 'isoformat'):  # datetime objects
        return result.isoformat()
    return result


# Tool implementations
@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="create_fabric",
            description="Create a new fabric with code, name, and optional image URL",
            inputSchema=CreateFabricInput.model_json_schema()
        ),
        Tool(
            name="search_fabrics",
            description="Search fabrics with optional filters and pagination",
            inputSchema=SearchFabricsInput.model_json_schema()
        ),
        Tool(
            name="create_variant",
            description="Create a new fabric variant with color, GSM, width, and finish",
            inputSchema=CreateVariantInput.model_json_schema()
        ),
        Tool(
            name="get_variant",
            description="Get variant details by ID, including joined fabric information",
            inputSchema=GetVariantInput.model_json_schema()
        ),
        Tool(
            name="search_variants",
            description="Search variants with filters, optional stock information, and pagination",
            inputSchema=SearchVariantsInput.model_json_schema()
        ),
        Tool(
            name="receive_stock",
            description="Record a receipt of fabric stock (increases inventory)",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="issue_stock",
            description="Record an issue/consumption of fabric stock (decreases inventory)",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="adjust_stock",
            description="Record a stock adjustment (can be positive or negative)",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="get_stock",
            description="Get current stock balance for a variant with roll/meter calculations",
            inputSchema=GetStockInput.model_json_schema()
        ),
        Tool(
            name="get_stock_batch",
            description="Get stock balances for multiple variants at once",
            inputSchema=GetStockBatchInput.model_json_schema()
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "create_fabric":
            args = CreateFabricInput(**arguments)
            result = repo.create_fabric(
                fabric_code=args.fabric_code,
                name=args.name,
                image_url=args.image_url
            )
            return [TextContent(
                type="text",
                text=f"Fabric created successfully:\n{serialize_result(result)}"
            )]

        elif name == "search_fabrics":
            args = SearchFabricsInput(**arguments)
            items, total = repo.search_fabrics(
                q=args.q,
                fabric_code=args.fabric_code,
                name=args.name,
                limit=args.limit,
                offset=args.offset
            )
            result = {
                "items": serialize_result(items),
                "total": total,
                "limit": args.limit,
                "offset": args.offset
            }
            return [TextContent(
                type="text",
                text=f"Found {total} fabrics:\n{result}"
            )]

        elif name == "create_variant":
            args = CreateVariantInput(**arguments)
            result = repo.create_variant(
                fabric_id=args.fabric_id,
                color_code=args.color_code,
                gsm=args.gsm,
                width=args.width,
                finish=args.finish,
                image_url=args.image_url
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric with id {args.fabric_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Variant created successfully:\n{serialize_result(result)}"
            )]

        elif name == "get_variant":
            args = GetVariantInput(**arguments)
            result = repo.get_variant_detail(args.variant_id)
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant with id {args.variant_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Variant details:\n{serialize_result(result)}"
            )]

        elif name == "search_variants":
            args = SearchVariantsInput(**arguments)
            items, total = repo.search_variants(
                q=args.q,
                fabric_id=args.fabric_id,
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                gsm=args.gsm,
                gsm_min=args.gsm_min,
                gsm_max=args.gsm_max,
                include_stock=args.include_stock,
                in_stock_only=args.in_stock_only,
                limit=args.limit,
                offset=args.offset
            )
            result = {
                "items": serialize_result(items),
                "total": total,
                "limit": args.limit,
                "offset": args.offset
            }
            return [TextContent(
                type="text",
                text=f"Found {total} variants:\n{result}"
            )]

        elif name == "receive_stock":
            args = MovementInput(**arguments)
            result = repo.create_movement(
                variant_id=args.variant_id,
                movement_type="RECEIPT",
                qty=args.qty,
                uom=args.uom,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant with id {args.variant_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Stock received successfully:\n{serialize_result(result)}"
            )]

        elif name == "issue_stock":
            args = MovementInput(**arguments)
            result = repo.create_movement(
                variant_id=args.variant_id,
                movement_type="ISSUE",
                qty=-abs(args.qty),  # Always negative for issues
                uom=args.uom,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant with id {args.variant_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Stock issued successfully:\n{serialize_result(result)}"
            )]

        elif name == "adjust_stock":
            args = MovementInput(**arguments)
            result = repo.create_movement(
                variant_id=args.variant_id,
                movement_type="ADJUST",
                qty=args.qty,
                uom=args.uom,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant with id {args.variant_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Stock adjusted successfully:\n{serialize_result(result)}"
            )]

        elif name == "get_stock":
            args = GetStockInput(**arguments)
            result = repo.get_stock_balance(args.variant_id, args.uom)
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant with id {args.variant_id} not found"
                )]
            return [TextContent(
                type="text",
                text=f"Stock balance:\n{serialize_result(result)}"
            )]

        elif name == "get_stock_batch":
            args = GetStockBatchInput(**arguments)
            results = repo.get_stock_balances_batch(args.variant_ids, args.uom)
            return [TextContent(
                type="text",
                text=f"Stock balances for {len(results)} variants:\n{serialize_result(results)}"
            )]

        else:
            return [TextContent(
                type="text",
                text=f"Error: Unknown tool '{name}'"
            )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error executing {name}: {str(e)}"
        )]


async def main():
    """Run the MCP server."""
    # Initialize database
    init_db()

    try:
        # Run the server using stdio transport
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options()
            )
    finally:
        # Clean up database connections
        close_db()


if __name__ == "__main__":
    asyncio.run(main())
