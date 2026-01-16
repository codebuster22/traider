"""Pydantic models for API request/response schemas."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Gallery
# ============================================================================

class GalleryPhotoshoot(BaseModel):
    """A photoshoot namespace with main image and gallery."""
    main: str
    images: list[str] = Field(default_factory=list)


# Gallery is a dict mapping namespace (e.g., "photoshoot1") to GalleryPhotoshoot
Gallery = dict[str, GalleryPhotoshoot]


# ============================================================================
# Fabrics
# ============================================================================

class FabricCreate(BaseModel):
    fabric_code: str
    name: str
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)


class Fabric(BaseModel):
    id: int
    fabric_code: str
    name: str
    image_url: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)


class FabricUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    gallery: Optional[Gallery] = None


# ============================================================================
# Aliases
# ============================================================================

class AliasCreate(BaseModel):
    alias: str


# ============================================================================
# Variants
# ============================================================================

class VariantCreate(BaseModel):
    color_code: str
    finish: str = "Standard"
    gsm: Optional[int] = None
    width: Optional[int] = None
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)


class Variant(BaseModel):
    id: int
    fabric_id: int
    color_code: str
    finish: str
    gsm: Optional[int] = None
    width: Optional[int] = None
    image_url: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)


class VariantUpdate(BaseModel):
    color_code: Optional[str] = None
    gsm: Optional[int] = None
    width: Optional[int] = None
    finish: Optional[str] = None
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    gallery: Optional[Gallery] = None


class VariantDetail(BaseModel):
    """Variant with joined fabric basics."""
    id: int
    fabric_id: int
    fabric_code: str
    fabric_name: str
    fabric_image_url: Optional[str] = None
    fabric_gallery: Gallery = Field(default_factory=dict)
    color_code: str
    finish: str
    gsm: Optional[int] = None
    width: Optional[int] = None
    variant_image_url: Optional[str] = None
    variant_gallery: Gallery = Field(default_factory=dict)


# ============================================================================
# Movements
# ============================================================================

class MovementCreate(BaseModel):
    fabric_code: str
    color_code: str
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int] = None
    document_id: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v):
        # Allow qty=0 when only adjusting roll_count
        return v


class MovementResponse(BaseModel):
    movement_id: int
    movement_type: str
    delta_qty_m: float
    on_hand_m_after: float


# --- Movement History ---

class MovementHistoryItem(BaseModel):
    """Single movement record with fabric/color details."""
    id: int
    ts: datetime
    fabric_code: str
    color_code: str
    movement_type: str
    delta_qty_m: float
    original_qty: float
    original_uom: str
    roll_count: Optional[int] = None
    document_id: Optional[str] = None
    reason: Optional[str] = None
    is_cancelled: bool
    cancelled_at: Optional[datetime] = None
    created_at: datetime


class MovementHistoryResponse(BaseModel):
    """Paginated movement history response."""
    items: list[MovementHistoryItem]
    total: int
    limit: int
    offset: int


# --- Cancel Movement ---

class CancelMovementRequest(BaseModel):
    """Request to cancel a movement."""
    reason: Optional[str] = None


class CancelMovementResponse(BaseModel):
    """Response after cancelling a movement."""
    message: str
    movement_id: int
    reversed_qty_m: float
    new_balance_m: float
    cancelled_at: datetime


# ============================================================================
# Stock
# ============================================================================

class StockBalance(BaseModel):
    """Stock balance for a variant with full details."""
    variant_id: int
    fabric_id: int
    fabric_code: str
    fabric_name: str
    fabric_image_url: Optional[str] = None
    fabric_gallery: Gallery = Field(default_factory=dict)
    color_code: str
    finish: str
    gsm: Optional[int] = None
    width: Optional[int] = None
    variant_image_url: Optional[str] = None
    variant_gallery: Gallery = Field(default_factory=dict)

    on_hand_m: float
    on_hand_rolls: float

    uom: str
    updated_at: datetime


# ============================================================================
# Search
# ============================================================================

class FabricSearchResult(BaseModel):
    items: list[Fabric]
    limit: int
    offset: int
    total: int


class VariantSearchItem(BaseModel):
    """Variant search result item (may include stock)."""
    id: int
    fabric_id: int
    fabric_code: str
    fabric_name: str
    fabric_image_url: Optional[str] = None
    fabric_gallery: Gallery = Field(default_factory=dict)
    color_code: str
    finish: str
    gsm: Optional[int] = None
    width: Optional[int] = None
    variant_image_url: Optional[str] = None
    variant_gallery: Gallery = Field(default_factory=dict)

    # Optional stock fields
    on_hand_m: Optional[float] = None
    on_hand_rolls: Optional[float] = None
    updated_at: Optional[datetime] = None


class VariantSearchResult(BaseModel):
    items: list[VariantSearchItem]
    limit: int
    offset: int
    total: int


# ============================================================================
# Unified Search
# ============================================================================

class FabricSearchItem(BaseModel):
    """Fabric search result with match info."""
    fabric_code: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)
    match_source: str  # "name", "fabric_code", or "alias"


class UnifiedSearchResult(BaseModel):
    """Combined search results for fabrics and variants."""
    fabrics: list[FabricSearchItem] = Field(default_factory=list)
    variants: list[VariantSearchItem] = Field(default_factory=list)


# ============================================================================
# Batch Operations
# ============================================================================

# --- Batch Variant Creation ---

class VariantBatchItem(BaseModel):
    """Single variant item for batch creation."""
    color_code: str
    finish: str = "Standard"
    gsm: Optional[int] = None
    width: Optional[int] = None


class VariantBatchRequest(BaseModel):
    """Request for batch variant creation."""
    variants: list[VariantBatchItem]


class VariantBatchCreatedItem(BaseModel):
    """Successfully created variant in batch response."""
    fabric_code: str
    color_code: str
    finish: str


class VariantBatchFailedItem(BaseModel):
    """Failed variant in batch response."""
    color_code: str
    error: str


class BatchSummary(BaseModel):
    """Summary statistics for batch operations."""
    total: int
    created: int = 0
    processed: int = 0
    failed: int
    found: int = 0
    not_found: int = 0


class VariantBatchResponse(BaseModel):
    """Response for batch variant creation."""
    created: list[VariantBatchCreatedItem]
    failed: list[VariantBatchFailedItem]
    summary: BatchSummary


# --- Batch Stock Movements ---

class MovementBatchItem(BaseModel):
    """Single movement item for batch stock operations."""
    fabric_code: str
    color_code: str
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int] = None


class MovementBatchRequest(BaseModel):
    """Request for batch stock movements."""
    items: list[MovementBatchItem]
    document_id: Optional[str] = None
    reason: Optional[str] = None
    customer_name: Optional[str] = None  # For issue


class MovementBatchProcessedItem(BaseModel):
    """Successfully processed movement in batch response."""
    fabric_code: str
    color_code: str
    qty: float
    previous_balance: float
    new_balance: float
    movement_id: int


class MovementBatchFailedItem(BaseModel):
    """Failed movement in batch response."""
    fabric_code: str
    color_code: str
    qty: float
    error: str


class MovementBatchSummary(BaseModel):
    """Summary statistics for batch movement operations."""
    total: int
    processed: int
    failed: int
    total_qty: float = 0


class MovementBatchResponse(BaseModel):
    """Response for batch stock movements."""
    processed: list[MovementBatchProcessedItem]
    failed: list[MovementBatchFailedItem]
    summary: MovementBatchSummary


# --- Batch Variant Search ---

class VariantSearchBatchRequest(BaseModel):
    """Request for batch variant search."""
    color_codes: list[str]
    include_stock: bool = False


class VariantSearchBatchFoundItem(BaseModel):
    """Found variant in batch search response."""
    color_code: str
    variant: VariantSearchItem
    stock: Optional[dict] = None


class VariantSearchBatchResponse(BaseModel):
    """Response for batch variant search."""
    found: list[VariantSearchBatchFoundItem]
    not_found: list[str]
    summary: BatchSummary


# ============================================================================
# Utility Responses
# ============================================================================

class MessageResponse(BaseModel):
    """Generic message response for simple operations."""
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str


class ImageUploadResponse(BaseModel):
    """Response from image upload endpoint."""
    url: str
    secure_url: str
    public_id: str
