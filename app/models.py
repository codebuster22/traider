"""Pydantic models for API request/response schemas."""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Fabrics
# ============================================================================

class FabricCreate(BaseModel):
    fabric_code: str
    name: str
    image_url: Optional[str] = None


class Fabric(BaseModel):
    id: int
    fabric_code: str
    name: str
    image_url: Optional[str] = None


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


class Variant(BaseModel):
    id: int
    fabric_id: int
    color_code: str
    gsm: int
    width: int
    finish: str
    image_url: Optional[str] = None


class VariantDetail(BaseModel):
    """Variant with joined fabric basics."""
    id: int
    fabric_id: int
    fabric_code: str
    fabric_name: str
    fabric_image_url: Optional[str] = None
    color_code: str
    gsm: int
    width: int
    finish: str
    variant_image_url: Optional[str] = None


# ============================================================================
# Movements
# ============================================================================

class MovementCreate(BaseModel):
    variant_id: int
    qty: float
    uom: Literal["m", "roll"]
    reason: Optional[str] = None

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v):
        if v == 0:
            raise ValueError("qty cannot be zero")
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
    color_code: str
    gsm: int
    width: int
    finish: str
    variant_image_url: Optional[str] = None

    on_hand_m: float
    on_hand_rolls: float
    whole_rolls: int
    remainder_m: float

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
    color_code: str
    gsm: int
    width: int
    finish: str
    variant_image_url: Optional[str] = None

    # Optional stock fields
    on_hand_m: Optional[float] = None
    on_hand_rolls: Optional[float] = None
    whole_rolls: Optional[int] = None
    remainder_m: Optional[float] = None
    updated_at: Optional[datetime] = None


class VariantSearchResult(BaseModel):
    items: list[VariantSearchItem]
    limit: int
    offset: int
    total: int
