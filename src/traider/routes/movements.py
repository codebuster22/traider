"""Routes for stock movements."""
from fastapi import APIRouter, HTTPException

from traider.models import MovementCreate, MovementResponse
from traider import repo

router = APIRouter(tags=["movements"])


@router.post("/receive", response_model=MovementResponse, status_code=201)
def receive(movement: MovementCreate):
    """Record a receipt of fabric."""
    result = repo.create_movement(
        variant_id=movement.variant_id,
        movement_type="RECEIPT",
        qty=movement.qty,
        uom=movement.uom,
        roll_count=movement.roll_count,
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {movement.variant_id} not found")
    return result


@router.post("/issue", response_model=MovementResponse, status_code=201)
def issue(movement: MovementCreate):
    """Record an issue/consumption of fabric."""
    # For ISSUE, negate the quantity to reduce stock
    result = repo.create_movement(
        variant_id=movement.variant_id,
        movement_type="ISSUE",
        qty=-abs(movement.qty),  # Always negative for issues
        uom=movement.uom,
        roll_count=-abs(movement.roll_count) if movement.roll_count is not None else None,  # Also negative for rolls
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {movement.variant_id} not found")
    return result


@router.post("/adjust", response_model=MovementResponse, status_code=201)
def adjust(movement: MovementCreate):
    """Record a stock adjustment (can be positive or negative)."""
    result = repo.create_movement(
        variant_id=movement.variant_id,
        movement_type="ADJUST",
        qty=movement.qty,
        uom=movement.uom,
        roll_count=movement.roll_count,
        document_id=movement.document_id,
        reason=movement.reason
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variant with id {movement.variant_id} not found")
    return result
