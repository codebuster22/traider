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


class Fabric(BaseModel):
    id: int
    fabric_code: str
    name: str
    image_url: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)


# ============================================================================
# Variants
# ============================================================================

class VariantCreate(BaseModel):
    fabric_id: int
    color_code: str
    gsm: int
    width: int
    finish: str
    image_url: Optional[str] = None
    image_data: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)


class Variant(BaseModel):
    id: int
    fabric_id: int
    color_code: str
    gsm: int
    width: int
    finish: str
    image_url: Optional[str] = None
    gallery: Gallery = Field(default_factory=dict)


class VariantDetail(BaseModel):
    """Variant with joined fabric basics."""
    id: int
    fabric_id: int
    fabric_code: str
    fabric_name: str
    fabric_image_url: Optional[str] = None
    fabric_gallery: Gallery = Field(default_factory=dict)
    color_code: str
    gsm: int
    width: int
    finish: str
    variant_image_url: Optional[str] = None
    variant_gallery: Gallery = Field(default_factory=dict)


# ============================================================================
# Movements
# ============================================================================

class MovementCreate(BaseModel):
    variant_id: int
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
    gsm: int
    width: int
    finish: str
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
    gsm: int
    width: int
    finish: str
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
