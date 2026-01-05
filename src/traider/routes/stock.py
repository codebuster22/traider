"""Routes for stock queries."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from traider.models import StockBalance
from traider import repo

router = APIRouter(prefix="/stock", tags=["stock"])


# ============================================================================
# Primary route using business identifiers
# ============================================================================

@router.get("/{fabric_code}/{color_code}", response_model=StockBalance)
def get_stock_by_codes(
    fabric_code: str,
    color_code: str,
    uom: str = Query("m", description="Unit of measure for display: m or roll")
):
    """Get stock balance using fabric_code and color_code."""
    if uom not in {"m", "roll"}:
        raise HTTPException(status_code=400, detail="uom must be 'm' or 'roll'")

    result = repo.get_stock_balance_by_codes(fabric_code, color_code, uom)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{color_code}' not found for fabric '{fabric_code}'"
        )

    return result


# ============================================================================
# Fallback routes using internal IDs
# ============================================================================

@router.get("", response_model=StockBalance)
def get_stock(
    variant_id: int = Query(..., description="Variant ID to get stock for"),
    uom: str = Query("m", description="Unit of measure for display: m or roll")
):
    """Get stock balance for a specific variant by ID (fallback)."""
    if uom not in {"m", "roll"}:
        raise HTTPException(status_code=400, detail="uom must be 'm' or 'roll'")

    result = repo.get_stock_balance(variant_id, uom)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {variant_id} not found")

    return result


@router.get("/batch", response_model=list[StockBalance])
def get_stock_batch(
    variant_ids: str = Query(..., description="Comma-separated variant IDs"),
    uom: str = Query("m", description="Unit of measure for display: m or roll")
):
    """Get stock balances for multiple variants by IDs (fallback)."""
    if uom not in {"m", "roll"}:
        raise HTTPException(status_code=400, detail="uom must be 'm' or 'roll'")

    # Parse variant IDs
    try:
        ids = [int(x.strip()) for x in variant_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid variant_ids format. Use comma-separated integers.")

    if not ids:
        raise HTTPException(status_code=400, detail="At least one variant_id is required")

    results = repo.get_stock_balances_batch(ids, uom)
    return results
