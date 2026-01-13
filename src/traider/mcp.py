"""MCP integration for FastAPI using SSE transport.

This module provides MCP (Model Context Protocol) tools via HTTP/SSE,
allowing AI clients like Claude to connect via URL instead of stdio.
"""
from typing import Any, Optional
from decimal import Decimal

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

from traider import repo
from traider.cloudinary_utils import upload_image as cloudinary_upload


# Initialize MCP server instance
mcp_server = Server("fabric-inventory")


# ============================================================================
# Tool Input Schemas
# ============================================================================

class UploadImageInput(BaseModel):
    image_data: str = Field(description="Base64 encoded image data (with or without data: URI prefix)")
    filename: Optional[str] = Field(None, description="Optional filename (without extension)")
    folder: str = Field("traider", description="Cloudinary folder path")


class CreateFabricInput(BaseModel):
    fabric_code: str = Field(description="Unique fabric code (e.g., 'FAB-001')")
    name: str = Field(description="Fabric name (e.g., 'Cotton Jersey')")
    image_url: Optional[str] = Field(None, description="Optional image URL (if already uploaded)")
    image_data: Optional[str] = Field(None, description="Optional base64 image data to upload")
    gallery: dict = Field(default_factory=dict, description="Gallery with photoshoot namespaces")
    aliases: list[str] = Field(default_factory=list, description="Alternative names for the fabric")


class UpdateFabricInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to update")
    name: Optional[str] = Field(None, description="New fabric name")
    image_url: Optional[str] = Field(None, description="New image URL (if already uploaded)")
    image_data: Optional[str] = Field(None, description="Optional base64 image data to upload")
    gallery: Optional[dict] = Field(None, description="New gallery data")


class AddAliasInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to add alias to")
    alias: str = Field(description="Alias to add")


class RemoveAliasInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to remove alias from")
    alias: str = Field(description="Alias to remove")


class GetFabricInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to retrieve")


class GetAliasesInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to get aliases for")


class SearchFabricsInput(BaseModel):
    q: Optional[str] = Field(None, description="Free text search across fabric_code, name, and aliases")
    fabric_code: Optional[str] = Field(None, description="Filter by fabric code (partial match)")
    name: Optional[str] = Field(None, description="Filter by name (partial match)")
    limit: int = Field(20, ge=1, le=100, description="Max results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")


class CreateVariantInput(BaseModel):
    fabric_code: str = Field(description="Fabric code of the parent fabric")
    color_code: str = Field(description="Color code (e.g., 'BLK-9001')")
    finish: str = Field("Standard", description="Finish type (e.g., 'Bio', 'Enzyme')")
    gsm: Optional[int] = Field(None, description="Grams per square meter (optional)")
    width: Optional[int] = Field(None, description="Width in inches (optional)")
    image_url: Optional[str] = Field(None, description="Optional image URL (if already uploaded)")
    image_data: Optional[str] = Field(None, description="Optional base64 image data to upload")
    gallery: dict = Field(default_factory=dict, description="Gallery with photoshoot namespaces")


class UpdateVariantInput(BaseModel):
    fabric_code: str = Field(description="Fabric code of the variant")
    color_code: str = Field(description="Color code of the variant to update")
    new_color_code: Optional[str] = Field(None, description="New color code (if renaming)")
    gsm: Optional[int] = Field(None, description="New GSM value")
    width: Optional[int] = Field(None, description="New width in inches")
    finish: Optional[str] = Field(None, description="New finish type")
    image_url: Optional[str] = Field(None, description="New image URL (if already uploaded)")
    image_data: Optional[str] = Field(None, description="Optional base64 image data to upload")
    gallery: Optional[dict] = Field(None, description="New gallery data")


class GetVariantInput(BaseModel):
    fabric_code: str = Field(description="Fabric code")
    color_code: str = Field(description="Color code")


class DeleteVariantInput(BaseModel):
    fabric_code: str = Field(description="Fabric code")
    color_code: str = Field(description="Color code of the variant to delete")


class SearchVariantsInput(BaseModel):
    q: Optional[str] = Field(None, description="Free text search")
    fabric_code: Optional[str] = Field(None, description="Filter by fabric code")
    color_code: Optional[str] = Field(None, description="Filter by color code")
    gsm: Optional[int] = Field(None, description="Filter by exact GSM")
    gsm_min: Optional[int] = Field(None, description="Minimum GSM")
    gsm_max: Optional[int] = Field(None, description="Maximum GSM")
    width: Optional[int] = Field(None, description="Filter by exact width in inches")
    width_min: Optional[int] = Field(None, description="Minimum width in inches")
    width_max: Optional[int] = Field(None, description="Maximum width in inches")
    finish: Optional[str] = Field(None, description="Filter by finish type (partial match)")
    include_stock: bool = Field(False, description="Include stock information")
    in_stock_only: bool = Field(False, description="Only return variants with stock > 0")
    limit: int = Field(20, ge=1, le=100, description="Max results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")
    sort_by: str = Field("color_code", description="Sort field: id, fabric_code, color_code, gsm, width")
    sort_dir: str = Field("asc", description="Sort direction: asc or desc")


class MovementInput(BaseModel):
    fabric_code: str = Field(description="Fabric code")
    color_code: str = Field(description="Color code of the variant")
    qty: float = Field(description="Quantity in meters")
    uom: str = Field("m", description="Unit of measure: 'm' (meters)")
    roll_count: Optional[int] = Field(None, description="Number of rolls (optional, for tracking)")
    document_id: Optional[str] = Field(None, description="Invoice/receipt/document ID (optional)")
    reason: Optional[str] = Field(None, description="Free-text reason for the movement")


class GetStockInput(BaseModel):
    fabric_code: str = Field(description="Fabric code")
    color_code: str = Field(description="Color code")
    uom: str = Field("m", description="Unit of measure for display: 'm' or 'roll'")


class UnifiedSearchInput(BaseModel):
    q: str = Field(description="Search query")
    include_fabrics: bool = Field(True, description="Include fabrics in results")
    include_variants: bool = Field(True, description="Include variants in results")
    include_stock: bool = Field(False, description="Include stock info for variants")
    limit: int = Field(20, ge=1, le=100, description="Max results per category")


# Batch operation input schemas
class VariantBatchItemInput(BaseModel):
    color_code: str = Field(description="Color code for the variant")
    finish: str = Field("Standard", description="Finish type")
    gsm: Optional[int] = Field(None, description="Grams per square meter")
    width: Optional[int] = Field(None, description="Width in inches")


class CreateVariantsBatchInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to create variants under")
    variants: list[VariantBatchItemInput] = Field(description="List of variants to create (max 100)")


class MovementBatchItemInput(BaseModel):
    fabric_code: str = Field(description="Fabric code")
    color_code: str = Field(description="Color code")
    qty: float = Field(description="Quantity in meters")
    uom: str = Field("m", description="Unit of measure: 'm' or 'roll'")
    roll_count: Optional[int] = Field(None, description="Number of rolls")


class ReceiveStockBatchInput(BaseModel):
    items: list[MovementBatchItemInput] = Field(description="List of stock receipts (max 50)")
    document_id: Optional[str] = Field(None, description="Document/invoice ID")
    reason: Optional[str] = Field(None, description="Reason for receipt")


class IssueStockBatchInput(BaseModel):
    items: list[MovementBatchItemInput] = Field(description="List of stock issues (max 50)")
    document_id: Optional[str] = Field(None, description="Document/invoice ID")
    customer_name: Optional[str] = Field(None, description="Customer name")
    reason: Optional[str] = Field(None, description="Reason for issue")


class SearchVariantsBatchInput(BaseModel):
    fabric_code: str = Field(description="Fabric code to search within")
    color_codes: list[str] = Field(description="List of color codes to find")
    include_stock: bool = Field(False, description="Include stock balances")


# ============================================================================
# Helper Functions
# ============================================================================

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


# ============================================================================
# MCP Server Handlers
# ============================================================================

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="upload_image",
            description="Upload an image to Cloudinary and get back URLs",
            inputSchema=UploadImageInput.model_json_schema()
        ),
        Tool(
            name="create_fabric",
            description="Create a new fabric with code, name, optional image, and aliases",
            inputSchema=CreateFabricInput.model_json_schema()
        ),
        Tool(
            name="update_fabric",
            description="Update an existing fabric by fabric_code",
            inputSchema=UpdateFabricInput.model_json_schema()
        ),
        Tool(
            name="add_alias",
            description="Add an alternative name (alias) to a fabric for easier searching",
            inputSchema=AddAliasInput.model_json_schema()
        ),
        Tool(
            name="remove_alias",
            description="Remove an alias from a fabric",
            inputSchema=RemoveAliasInput.model_json_schema()
        ),
        Tool(
            name="get_fabric",
            description="Get a fabric by its fabric_code",
            inputSchema=GetFabricInput.model_json_schema()
        ),
        Tool(
            name="get_aliases",
            description="Get all aliases for a fabric by fabric_code",
            inputSchema=GetAliasesInput.model_json_schema()
        ),
        Tool(
            name="search_fabrics",
            description="Search fabrics by name, code, or aliases with pagination",
            inputSchema=SearchFabricsInput.model_json_schema()
        ),
        Tool(
            name="create_variant",
            description="Create a new fabric variant using fabric_code",
            inputSchema=CreateVariantInput.model_json_schema()
        ),
        Tool(
            name="update_variant",
            description="Update a variant using fabric_code + color_code",
            inputSchema=UpdateVariantInput.model_json_schema()
        ),
        Tool(
            name="get_variant",
            description="Get variant details by fabric_code + color_code",
            inputSchema=GetVariantInput.model_json_schema()
        ),
        Tool(
            name="delete_variant",
            description="Delete a variant by fabric_code + color_code",
            inputSchema=DeleteVariantInput.model_json_schema()
        ),
        Tool(
            name="search_variants",
            description="Search variants with filters, optional stock info, and pagination",
            inputSchema=SearchVariantsInput.model_json_schema()
        ),
        Tool(
            name="receive_stock",
            description="Record a receipt of fabric stock using fabric_code + color_code",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="issue_stock",
            description="Record an issue of fabric stock using fabric_code + color_code",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="adjust_stock",
            description="Record a stock adjustment using fabric_code + color_code",
            inputSchema=MovementInput.model_json_schema()
        ),
        Tool(
            name="get_stock",
            description="Get stock balance using fabric_code + color_code",
            inputSchema=GetStockInput.model_json_schema()
        ),
        Tool(
            name="unified_search",
            description="Search across fabrics (including aliases) and variants in one call",
            inputSchema=UnifiedSearchInput.model_json_schema()
        ),
        # Batch operations
        Tool(
            name="create_variants_batch",
            description="Create multiple variants under a single fabric (max 100). Returns created and failed lists.",
            inputSchema=CreateVariantsBatchInput.model_json_schema()
        ),
        Tool(
            name="receive_stock_batch",
            description="Record stock inflow for multiple variants (max 50). Returns processed and failed lists.",
            inputSchema=ReceiveStockBatchInput.model_json_schema()
        ),
        Tool(
            name="issue_stock_batch",
            description="Record stock outflow for multiple variants (max 50). Negative stock allowed. Returns processed and failed lists.",
            inputSchema=IssueStockBatchInput.model_json_schema()
        ),
        Tool(
            name="search_variants_batch",
            description="Search multiple variants by color codes within a fabric. Returns found variants and not found list.",
            inputSchema=SearchVariantsBatchInput.model_json_schema()
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "upload_image":
            args = UploadImageInput(**arguments)
            try:
                upload_result = cloudinary_upload(
                    image_data=args.image_data,
                    folder=args.folder,
                    filename=args.filename
                )
                return [TextContent(
                    type="text",
                    text=f"Image uploaded successfully:\n"
                         f"URL: {upload_result['secure_url']}\n"
                         f"Thumbnail: {upload_result['thumbnail_url']}\n"
                         f"Size: {upload_result['width']}x{upload_result['height']}\n"
                         f"Format: {upload_result['format']}\n"
                         f"Public ID: {upload_result['public_id']}"
                )]
            except Exception as e:
                return [TextContent(
                    type="text",
                    text=f"Error uploading image: {str(e)}"
                )]

        elif name == "create_fabric":
            args = CreateFabricInput(**arguments)

            # Handle inline image upload
            image_url = args.image_url
            if args.image_data:
                try:
                    upload_result = cloudinary_upload(
                        image_data=args.image_data,
                        folder="traider/fabrics",
                        filename=args.fabric_code
                    )
                    image_url = upload_result['secure_url']
                except Exception as e:
                    return [TextContent(
                        type="text",
                        text=f"Error uploading image: {str(e)}"
                    )]

            result = repo.create_fabric(
                fabric_code=args.fabric_code,
                name=args.name,
                image_url=image_url,
                gallery=args.gallery,
                aliases=args.aliases
            )
            return [TextContent(
                type="text",
                text=f"Fabric created successfully:\n{serialize_result(result)}"
            )]

        elif name == "update_fabric":
            args = UpdateFabricInput(**arguments)

            # Get fabric first to find its ID
            fabric = repo.get_fabric_by_code(args.fabric_code)
            if fabric is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]

            # Handle inline image upload
            image_url = args.image_url
            if args.image_data:
                try:
                    upload_result = cloudinary_upload(
                        image_data=args.image_data,
                        folder="traider/fabrics",
                        filename=args.fabric_code
                    )
                    image_url = upload_result['secure_url']
                except Exception as e:
                    return [TextContent(
                        type="text",
                        text=f"Error uploading image: {str(e)}"
                    )]

            result = repo.update_fabric(
                fabric_id=fabric["id"],
                name=args.name,
                image_url=image_url,
                gallery=args.gallery
            )
            return [TextContent(
                type="text",
                text=f"Fabric updated successfully:\n{serialize_result(result)}"
            )]

        elif name == "add_alias":
            args = AddAliasInput(**arguments)
            fabric = repo.get_fabric_by_code(args.fabric_code)
            if fabric is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]

            added = repo.add_fabric_alias(fabric["id"], args.alias)
            if added:
                return [TextContent(
                    type="text",
                    text=f"Alias '{args.alias}' added to fabric '{args.fabric_code}'"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Alias '{args.alias}' already exists for fabric '{args.fabric_code}'"
                )]

        elif name == "remove_alias":
            args = RemoveAliasInput(**arguments)
            fabric = repo.get_fabric_by_code(args.fabric_code)
            if fabric is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]

            removed = repo.remove_fabric_alias(fabric["id"], args.alias)
            if removed:
                return [TextContent(
                    type="text",
                    text=f"Alias '{args.alias}' removed from fabric '{args.fabric_code}'"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Alias '{args.alias}' not found for fabric '{args.fabric_code}'"
                )]

        elif name == "get_fabric":
            args = GetFabricInput(**arguments)
            result = repo.get_fabric_by_code(args.fabric_code)
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]
            return [TextContent(
                type="text",
                text=f"Fabric details:\n{serialize_result(result)}"
            )]

        elif name == "get_aliases":
            args = GetAliasesInput(**arguments)
            fabric = repo.get_fabric_by_code(args.fabric_code)
            if fabric is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]
            aliases = repo.get_fabric_aliases(fabric["id"])
            return [TextContent(
                type="text",
                text=f"Aliases for '{args.fabric_code}': {aliases}"
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

            # Handle inline image upload
            image_url = args.image_url
            if args.image_data:
                try:
                    upload_result = cloudinary_upload(
                        image_data=args.image_data,
                        folder="traider/variants",
                        filename=f"{args.fabric_code}_{args.color_code}"
                    )
                    image_url = upload_result['secure_url']
                except Exception as e:
                    return [TextContent(
                        type="text",
                        text=f"Error uploading image: {str(e)}"
                    )]

            result = repo.create_variant_by_fabric_code(
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                gsm=args.gsm,
                width=args.width,
                finish=args.finish,
                image_url=image_url,
                gallery=args.gallery
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]
            return [TextContent(
                type="text",
                text=f"Variant created successfully:\n{serialize_result(result)}"
            )]

        elif name == "update_variant":
            args = UpdateVariantInput(**arguments)

            # Handle inline image upload
            image_url = args.image_url
            if args.image_data:
                try:
                    upload_result = cloudinary_upload(
                        image_data=args.image_data,
                        folder="traider/variants",
                        filename=f"{args.fabric_code}_{args.color_code}"
                    )
                    image_url = upload_result['secure_url']
                except Exception as e:
                    return [TextContent(
                        type="text",
                        text=f"Error uploading image: {str(e)}"
                    )]

            result = repo.update_variant_by_codes(
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                new_color_code=args.new_color_code,
                gsm=args.gsm,
                width=args.width,
                finish=args.finish,
                image_url=image_url,
                gallery=args.gallery
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Variant updated successfully:\n{serialize_result(result)}"
            )]

        elif name == "get_variant":
            args = GetVariantInput(**arguments)
            result = repo.get_variant_by_codes(args.fabric_code, args.color_code)
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Variant details:\n{serialize_result(result)}"
            )]

        elif name == "delete_variant":
            args = DeleteVariantInput(**arguments)
            deleted = repo.delete_variant_by_codes(args.fabric_code, args.color_code)
            if deleted:
                return [TextContent(
                    type="text",
                    text=f"Variant '{args.color_code}' deleted from fabric '{args.fabric_code}'"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]

        elif name == "search_variants":
            args = SearchVariantsInput(**arguments)
            items, total = repo.search_variants(
                q=args.q,
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                gsm=args.gsm,
                gsm_min=args.gsm_min,
                gsm_max=args.gsm_max,
                width=args.width,
                width_min=args.width_min,
                width_max=args.width_max,
                finish=args.finish,
                include_stock=args.include_stock,
                in_stock_only=args.in_stock_only,
                limit=args.limit,
                offset=args.offset,
                sort_by=args.sort_by,
                sort_dir=args.sort_dir
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
            result = repo.create_movement_by_codes(
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                movement_type="RECEIPT",
                qty=args.qty,
                uom=args.uom,
                roll_count=args.roll_count,
                document_id=args.document_id,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Stock received successfully:\n{serialize_result(result)}"
            )]

        elif name == "issue_stock":
            args = MovementInput(**arguments)
            result = repo.create_movement_by_codes(
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                movement_type="ISSUE",
                qty=-abs(args.qty),  # Always negative for issues
                uom=args.uom,
                roll_count=-abs(args.roll_count) if args.roll_count is not None else None,
                document_id=args.document_id,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Stock issued successfully:\n{serialize_result(result)}"
            )]

        elif name == "adjust_stock":
            args = MovementInput(**arguments)
            result = repo.create_movement_by_codes(
                fabric_code=args.fabric_code,
                color_code=args.color_code,
                movement_type="ADJUST",
                qty=args.qty,
                uom=args.uom,
                roll_count=args.roll_count,
                document_id=args.document_id,
                reason=args.reason
            )
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Stock adjusted successfully:\n{serialize_result(result)}"
            )]

        elif name == "get_stock":
            args = GetStockInput(**arguments)
            result = repo.get_stock_balance_by_codes(args.fabric_code, args.color_code, args.uom)
            if result is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Variant '{args.color_code}' not found for fabric '{args.fabric_code}'"
                )]
            return [TextContent(
                type="text",
                text=f"Stock balance:\n{serialize_result(result)}"
            )]

        elif name == "unified_search":
            args = UnifiedSearchInput(**arguments)
            result = repo.unified_search(
                q=args.q,
                include_fabrics=args.include_fabrics,
                include_variants=args.include_variants,
                include_stock=args.include_stock,
                limit=args.limit
            )
            return [TextContent(
                type="text",
                text=f"Search results:\n"
                     f"Fabrics: {len(result['fabrics'])}\n"
                     f"Variants: {len(result['variants'])}\n"
                     f"Data: {serialize_result(result)}"
            )]

        # Batch operations
        elif name == "create_variants_batch":
            args = CreateVariantsBatchInput(**arguments)

            if len(args.variants) > 100:
                return [TextContent(
                    type="text",
                    text="Error: Max batch size is 100 variants"
                )]

            if len(args.variants) == 0:
                return [TextContent(
                    type="text",
                    text="Error: At least one variant is required"
                )]

            # Convert to dicts
            variants = [v.model_dump() for v in args.variants]

            fabric_id, created, failed = repo.create_variants_batch(args.fabric_code, variants)

            if fabric_id is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]

            result = {
                "created": created,
                "failed": failed,
                "summary": {
                    "total": len(args.variants),
                    "created": len(created),
                    "failed": len(failed)
                }
            }

            return [TextContent(
                type="text",
                text=f"Batch create completed:\n"
                     f"Created: {len(created)}, Failed: {len(failed)}\n"
                     f"Data: {serialize_result(result)}"
            )]

        elif name == "receive_stock_batch":
            args = ReceiveStockBatchInput(**arguments)

            if len(args.items) > 50:
                return [TextContent(
                    type="text",
                    text="Error: Max batch size is 50 items"
                )]

            if len(args.items) == 0:
                return [TextContent(
                    type="text",
                    text="Error: At least one item is required"
                )]

            # Convert to dicts
            items = [item.model_dump() for item in args.items]

            processed, failed = repo.create_movements_batch(
                items=items,
                movement_type="RECEIPT",
                document_id=args.document_id,
                reason=args.reason
            )

            total_qty = sum(p["qty"] for p in processed)

            result = {
                "processed": processed,
                "failed": failed,
                "summary": {
                    "total": len(args.items),
                    "processed": len(processed),
                    "failed": len(failed),
                    "total_qty": total_qty
                }
            }

            return [TextContent(
                type="text",
                text=f"Batch receive completed:\n"
                     f"Processed: {len(processed)}, Failed: {len(failed)}, Total qty: {total_qty}\n"
                     f"Data: {serialize_result(result)}"
            )]

        elif name == "issue_stock_batch":
            args = IssueStockBatchInput(**arguments)

            if len(args.items) > 50:
                return [TextContent(
                    type="text",
                    text="Error: Max batch size is 50 items"
                )]

            if len(args.items) == 0:
                return [TextContent(
                    type="text",
                    text="Error: At least one item is required"
                )]

            # Convert to dicts with negated quantities
            items = []
            for item in args.items:
                item_dict = item.model_dump()
                item_dict["qty"] = -abs(item_dict["qty"])
                if item_dict.get("roll_count") is not None:
                    item_dict["roll_count"] = -abs(item_dict["roll_count"])
                items.append(item_dict)

            # Build reason with customer_name
            reason = args.reason
            if args.customer_name:
                reason = f"{args.customer_name}: {reason}" if reason else args.customer_name

            processed, failed = repo.create_movements_batch(
                items=items,
                movement_type="ISSUE",
                document_id=args.document_id,
                reason=reason
            )

            total_qty = sum(abs(p["qty"]) for p in processed)

            result = {
                "processed": processed,
                "failed": failed,
                "summary": {
                    "total": len(args.items),
                    "processed": len(processed),
                    "failed": len(failed),
                    "total_qty": total_qty
                }
            }

            return [TextContent(
                type="text",
                text=f"Batch issue completed:\n"
                     f"Processed: {len(processed)}, Failed: {len(failed)}, Total qty: {total_qty}\n"
                     f"Data: {serialize_result(result)}"
            )]

        elif name == "search_variants_batch":
            args = SearchVariantsBatchInput(**arguments)

            if len(args.color_codes) == 0:
                return [TextContent(
                    type="text",
                    text="Error: At least one color_code is required"
                )]

            fabric_id, found, not_found = repo.search_variants_batch(
                fabric_code=args.fabric_code,
                color_codes=args.color_codes,
                include_stock=args.include_stock
            )

            if fabric_id is None:
                return [TextContent(
                    type="text",
                    text=f"Error: Fabric '{args.fabric_code}' not found"
                )]

            result = {
                "found": found,
                "not_found": not_found,
                "summary": {
                    "total": len(args.color_codes),
                    "found": len(found),
                    "not_found": len(not_found)
                }
            }

            return [TextContent(
                type="text",
                text=f"Batch search completed:\n"
                     f"Found: {len(found)}, Not found: {len(not_found)}\n"
                     f"Data: {serialize_result(result)}"
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
