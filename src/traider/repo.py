"""Repository layer for database operations."""
from typing import Optional
from decimal import Decimal
import json
from traider.db import get_conn

# Constant for UOM conversion
ROLL_TO_M = 200


# ============================================================================
# Fabrics
# ============================================================================

def create_fabric(fabric_code: str, name: str, image_url: Optional[str] = None, gallery: Optional[dict] = None) -> dict:
    """Create a new fabric."""
    if gallery is None:
        gallery = {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fabrics (fabric_code, name, image_url, gallery)
                VALUES (%(fabric_code)s, %(name)s, %(image_url)s, %(gallery)s)
                RETURNING id, fabric_code, name, image_url, gallery
                """,
                {
                    "fabric_code": fabric_code,
                    "name": name,
                    "image_url": image_url,
                    "gallery": json.dumps(gallery)
                }
            )
            result = cur.fetchone()
        conn.commit()
        return result


def search_fabrics(
    q: Optional[str] = None,
    fabric_code: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "fabric_code",
    sort_dir: str = "asc"
) -> tuple[list[dict], int]:
    """Search fabrics with optional filters and pagination."""
    where_clauses = []
    params = {}

    if q:
        where_clauses.append("(fabric_code ILIKE %(q)s OR name ILIKE %(q)s)")
        params["q"] = f"%{q}%"

    if fabric_code:
        where_clauses.append("fabric_code ILIKE %(fabric_code)s")
        params["fabric_code"] = f"%{fabric_code}%"

    if name:
        where_clauses.append("name ILIKE %(name)s")
        params["name"] = f"%{name}%"

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Validate sort fields
    allowed_sort = {"id", "fabric_code", "name"}
    if sort_by not in allowed_sort:
        sort_by = "fabric_code"
    if sort_dir.lower() not in {"asc", "desc"}:
        sort_dir = "asc"

    params["limit"] = limit
    params["offset"] = offset

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(f"SELECT COUNT(*) as count FROM fabrics {where_sql}", params)
            total = cur.fetchone()["count"]

            # Get items
            cur.execute(
                f"""
                SELECT id, fabric_code, name, image_url, gallery
                FROM fabrics
                {where_sql}
                ORDER BY {sort_by} {sort_dir}
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params
            )
            items = cur.fetchall()

    return items, total


# ============================================================================
# Variants
# ============================================================================

def create_variant(
    fabric_id: int,
    color_code: str,
    gsm: int,
    width: int,
    finish: str,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None
) -> Optional[dict]:
    """Create a new variant. Returns None if fabric_id doesn't exist."""
    if gallery is None:
        gallery = {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check fabric exists
            cur.execute("SELECT id FROM fabrics WHERE id = %s", (fabric_id,))
            if not cur.fetchone():
                return None

            cur.execute(
                """
                INSERT INTO fabric_variants (fabric_id, color_code, gsm, width, finish, image_url, gallery)
                VALUES (%(fabric_id)s, %(color_code)s, %(gsm)s, %(width)s, %(finish)s, %(image_url)s, %(gallery)s)
                RETURNING id, fabric_id, color_code, gsm, width, finish, image_url, gallery
                """,
                {
                    "fabric_id": fabric_id,
                    "color_code": color_code,
                    "gsm": gsm,
                    "width": width,
                    "finish": finish,
                    "image_url": image_url,
                    "gallery": json.dumps(gallery)
                }
            )
            result = cur.fetchone()
        conn.commit()
        return result


def get_variant_detail(variant_id: int) -> Optional[dict]:
    """Get variant with joined fabric details."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    v.id,
                    v.fabric_id,
                    f.fabric_code,
                    f.name as fabric_name,
                    f.image_url as fabric_image_url,
                    f.gallery as fabric_gallery,
                    v.color_code,
                    v.gsm,
                    v.width,
                    v.finish,
                    v.image_url as variant_image_url,
                    v.gallery as variant_gallery
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                WHERE v.id = %s
                """,
                (variant_id,)
            )
            return cur.fetchone()


def search_variants(
    q: Optional[str] = None,
    fabric_id: Optional[int] = None,
    fabric_code: Optional[str] = None,
    color_code: Optional[str] = None,
    gsm: Optional[int] = None,
    gsm_min: Optional[int] = None,
    gsm_max: Optional[int] = None,
    width: Optional[int] = None,
    width_min: Optional[int] = None,
    width_max: Optional[int] = None,
    finish: Optional[str] = None,
    include_stock: bool = False,
    in_stock_only: bool = False,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "id",
    sort_dir: str = "asc"
) -> tuple[list[dict], int]:
    """Search variants with optional filters, stock, and pagination."""
    where_clauses = []
    params = {}

    if q:
        where_clauses.append(
            "(v.color_code ILIKE %(q)s OR v.finish ILIKE %(q)s OR f.fabric_code ILIKE %(q)s OR f.name ILIKE %(q)s)"
        )
        params["q"] = f"%{q}%"

    if fabric_id:
        where_clauses.append("v.fabric_id = %(fabric_id)s")
        params["fabric_id"] = fabric_id

    if fabric_code:
        where_clauses.append("f.fabric_code ILIKE %(fabric_code)s")
        params["fabric_code"] = f"%{fabric_code}%"

    if color_code:
        where_clauses.append("v.color_code ILIKE %(color_code)s")
        params["color_code"] = f"%{color_code}%"

    if gsm:
        where_clauses.append("v.gsm = %(gsm)s")
        params["gsm"] = gsm

    if gsm_min:
        where_clauses.append("v.gsm >= %(gsm_min)s")
        params["gsm_min"] = gsm_min

    if gsm_max:
        where_clauses.append("v.gsm <= %(gsm_max)s")
        params["gsm_max"] = gsm_max

    if width:
        where_clauses.append("v.width = %(width)s")
        params["width"] = width

    if width_min:
        where_clauses.append("v.width >= %(width_min)s")
        params["width_min"] = width_min

    if width_max:
        where_clauses.append("v.width <= %(width_max)s")
        params["width_max"] = width_max

    if finish:
        where_clauses.append("v.finish ILIKE %(finish)s")
        params["finish"] = f"%{finish}%"

    if in_stock_only:
        include_stock = True
        where_clauses.append("sb.on_hand_m > 0")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Stock join
    if include_stock:
        stock_join = "LEFT JOIN stock_balances sb ON v.id = sb.variant_id"
        stock_fields = ", sb.on_hand_m, sb.updated_at"
    else:
        stock_join = ""
        stock_fields = ""

    # Validate sort fields
    allowed_sort = {"id", "fabric_code", "color_code", "gsm", "width", "finish", "on_hand_m"}
    if sort_by not in allowed_sort:
        sort_by = "id"
    if sort_dir.lower() not in {"asc", "desc"}:
        sort_dir = "asc"

    # Map sort field to SQL column
    sort_map = {
        "id": "v.id",
        "fabric_code": "f.fabric_code",
        "color_code": "v.color_code",
        "gsm": "v.gsm",
        "width": "v.width",
        "finish": "v.finish",
        "on_hand_m": "sb.on_hand_m"
    }
    sort_col = sort_map.get(sort_by, "v.id")

    params["limit"] = limit
    params["offset"] = offset

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(
                f"""
                SELECT COUNT(*) as count
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                {stock_join}
                {where_sql}
                """,
                params
            )
            total = cur.fetchone()["count"]

            # Get items
            cur.execute(
                f"""
                SELECT
                    v.id,
                    v.fabric_id,
                    f.fabric_code,
                    f.name as fabric_name,
                    f.image_url as fabric_image_url,
                    f.gallery as fabric_gallery,
                    v.color_code,
                    v.gsm,
                    v.width,
                    v.finish,
                    v.image_url as variant_image_url,
                    v.gallery as variant_gallery
                    {stock_fields}
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                {stock_join}
                {where_sql}
                ORDER BY {sort_col} {sort_dir}
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params
            )
            items = cur.fetchall()

    # Calculate derived stock fields
    if include_stock:
        for item in items:
            if item.get("on_hand_m") is not None:
                on_hand_m = float(item["on_hand_m"])
                item["on_hand_rolls"] = on_hand_m / ROLL_TO_M
                item["whole_rolls"] = int(on_hand_m // ROLL_TO_M)
                item["remainder_m"] = on_hand_m - (item["whole_rolls"] * ROLL_TO_M)

    return items, total


# ============================================================================
# Movements
# ============================================================================

def create_movement(
    variant_id: int,
    movement_type: str,
    qty: float,
    uom: str,
    reason: Optional[str] = None
) -> Optional[dict]:
    """
    Create a movement and update stock balance.
    Returns dict with movement_id, movement_type, delta_qty_m, on_hand_m_after.
    Returns None if variant doesn't exist.
    """
    # Calculate delta in meters
    delta_qty_m = Decimal(str(qty)) if uom == "m" else Decimal(str(qty * ROLL_TO_M))

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check variant exists
            cur.execute("SELECT id FROM fabric_variants WHERE id = %s", (variant_id,))
            if not cur.fetchone():
                return None

            # Insert movement
            cur.execute(
                """
                INSERT INTO stock_movements (variant_id, movement_type, delta_qty_m, original_qty, original_uom, reason)
                VALUES (%(variant_id)s, %(movement_type)s, %(delta_qty_m)s, %(original_qty)s, %(original_uom)s, %(reason)s)
                RETURNING id
                """,
                {
                    "variant_id": variant_id,
                    "movement_type": movement_type,
                    "delta_qty_m": delta_qty_m,
                    "original_qty": Decimal(str(qty)),
                    "original_uom": uom,
                    "reason": reason
                }
            )
            movement_id = cur.fetchone()["id"]

            # Upsert balance
            cur.execute(
                """
                INSERT INTO stock_balances (variant_id, on_hand_m, updated_at)
                VALUES (%(variant_id)s, %(delta_qty_m)s, now())
                ON CONFLICT (variant_id) DO UPDATE
                SET on_hand_m = stock_balances.on_hand_m + EXCLUDED.on_hand_m,
                    updated_at = now()
                """,
                {"variant_id": variant_id, "delta_qty_m": delta_qty_m}
            )

            # Get updated balance
            cur.execute("SELECT on_hand_m FROM stock_balances WHERE variant_id = %s", (variant_id,))
            on_hand_m_after = cur.fetchone()["on_hand_m"]

        conn.commit()

        return {
            "movement_id": movement_id,
            "movement_type": movement_type,
            "delta_qty_m": float(delta_qty_m),
            "on_hand_m_after": float(on_hand_m_after)
        }


# ============================================================================
# Stock
# ============================================================================

def get_stock_balance(variant_id: int, uom: str = "m") -> Optional[dict]:
    """Get stock balance for a variant with full details."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    v.id as variant_id,
                    v.fabric_id,
                    f.fabric_code,
                    f.name as fabric_name,
                    f.image_url as fabric_image_url,
                    f.gallery as fabric_gallery,
                    v.color_code,
                    v.gsm,
                    v.width,
                    v.finish,
                    v.image_url as variant_image_url,
                    v.gallery as variant_gallery,
                    COALESCE(sb.on_hand_m, 0) as on_hand_m,
                    COALESCE(sb.updated_at, now()) as updated_at
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                LEFT JOIN stock_balances sb ON v.id = sb.variant_id
                WHERE v.id = %s
                """,
                (variant_id,)
            )
            result = cur.fetchone()

            if not result:
                return None

            # Calculate derived fields
            on_hand_m = float(result["on_hand_m"])
            on_hand_rolls = on_hand_m / ROLL_TO_M
            whole_rolls = int(on_hand_m // ROLL_TO_M)
            remainder_m = on_hand_m - (whole_rolls * ROLL_TO_M)

            return {
                **result,
                "on_hand_rolls": on_hand_rolls,
                "whole_rolls": whole_rolls,
                "remainder_m": remainder_m,
                "uom": uom
            }


def get_stock_balances_batch(variant_ids: list[int], uom: str = "m") -> list[dict]:
    """Get stock balances for multiple variants."""
    if not variant_ids:
        return []

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    v.id as variant_id,
                    v.fabric_id,
                    f.fabric_code,
                    f.name as fabric_name,
                    f.image_url as fabric_image_url,
                    f.gallery as fabric_gallery,
                    v.color_code,
                    v.gsm,
                    v.width,
                    v.finish,
                    v.image_url as variant_image_url,
                    v.gallery as variant_gallery,
                    COALESCE(sb.on_hand_m, 0) as on_hand_m,
                    COALESCE(sb.updated_at, now()) as updated_at
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                LEFT JOIN stock_balances sb ON v.id = sb.variant_id
                WHERE v.id = ANY(%s)
                """,
                (variant_ids,)
            )
            results = cur.fetchall()

            # Calculate derived fields
            for result in results:
                on_hand_m = float(result["on_hand_m"])
                on_hand_rolls = on_hand_m / ROLL_TO_M
                whole_rolls = int(on_hand_m // ROLL_TO_M)
                remainder_m = on_hand_m - (whole_rolls * ROLL_TO_M)

                result.update({
                    "on_hand_rolls": on_hand_rolls,
                    "whole_rolls": whole_rolls,
                    "remainder_m": remainder_m,
                    "uom": uom
                })

            return results
