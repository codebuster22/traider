"""Repository layer for database operations."""
from typing import Optional
from decimal import Decimal
import json
from traider.db import get_conn


# ============================================================================
# Fabrics
# ============================================================================

def create_fabric(
    fabric_code: str,
    name: str,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None,
    aliases: Optional[list[str]] = None
) -> dict:
    """Create a new fabric with optional aliases."""
    if gallery is None:
        gallery = {}
    if aliases is None:
        aliases = []

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
            result = dict(cur.fetchone())
            fabric_id = result["id"]

            # Add aliases
            if aliases:
                for alias in aliases:
                    cur.execute(
                        "INSERT INTO fabric_aliases (fabric_id, alias) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (fabric_id, alias)
                    )

            result["aliases"] = aliases
        conn.commit()
        return result


def update_fabric(
    fabric_id: int,
    name: Optional[str] = None,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None
) -> Optional[dict]:
    """Update a fabric. Returns None if fabric doesn't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check fabric exists
            cur.execute("SELECT id FROM fabrics WHERE id = %s", (fabric_id,))
            if not cur.fetchone():
                return None

            # Build dynamic update query
            updates = []
            params = {"id": fabric_id}

            if name is not None:
                updates.append("name = %(name)s")
                params["name"] = name

            if image_url is not None:
                updates.append("image_url = %(image_url)s")
                params["image_url"] = image_url

            if gallery is not None:
                updates.append("gallery = %(gallery)s")
                params["gallery"] = json.dumps(gallery)

            if not updates:
                # No updates provided, just return current fabric
                cur.execute(
                    "SELECT id, fabric_code, name, image_url, gallery FROM fabrics WHERE id = %(id)s",
                    params
                )
                return cur.fetchone()

            update_sql = f"UPDATE fabrics SET {', '.join(updates)} WHERE id = %(id)s RETURNING id, fabric_code, name, image_url, gallery"
            cur.execute(update_sql, params)
            result = cur.fetchone()
        conn.commit()
        return result


def get_fabric_by_code(fabric_code: str) -> Optional[dict]:
    """Get a fabric by its fabric_code with aliases."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, fabric_code, name, image_url, gallery
                FROM fabrics WHERE fabric_code = %s
                """,
                (fabric_code,)
            )
            fabric = cur.fetchone()
            if not fabric:
                return None

            fabric = dict(fabric)

            # Get aliases
            cur.execute(
                "SELECT alias FROM fabric_aliases WHERE fabric_id = %s ORDER BY alias",
                (fabric["id"],)
            )
            fabric["aliases"] = [row["alias"] for row in cur.fetchall()]
            return fabric


def get_fabric_aliases(fabric_id: int) -> list[str]:
    """Get all aliases for a fabric."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT alias FROM fabric_aliases WHERE fabric_id = %s ORDER BY alias",
                (fabric_id,)
            )
            return [row["alias"] for row in cur.fetchall()]


def add_fabric_alias(fabric_id: int, alias: str) -> bool:
    """Add an alias to a fabric. Returns True if added, False if already exists."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fabric_aliases (fabric_id, alias)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING fabric_id
                """,
                (fabric_id, alias)
            )
            result = cur.fetchone()
        conn.commit()
        return result is not None


def remove_fabric_alias(fabric_id: int, alias: str) -> bool:
    """Remove an alias from a fabric. Returns True if removed."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM fabric_aliases WHERE fabric_id = %s AND alias = %s RETURNING fabric_id",
                (fabric_id, alias)
            )
            result = cur.fetchone()
        conn.commit()
        return result is not None


def search_fabrics(
    q: Optional[str] = None,
    fabric_code: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "fabric_code",
    sort_dir: str = "asc"
) -> tuple[list[dict], int]:
    """Search fabrics with optional filters and pagination. Includes alias search."""
    where_clauses = []
    params = {}

    if q:
        # Search in fabric_code, name, AND aliases
        where_clauses.append("""
            (f.fabric_code ILIKE %(q)s OR f.name ILIKE %(q)s
             OR EXISTS (SELECT 1 FROM fabric_aliases fa WHERE fa.fabric_id = f.id AND fa.alias ILIKE %(q)s))
        """)
        params["q"] = f"%{q}%"

    if fabric_code:
        where_clauses.append("f.fabric_code ILIKE %(fabric_code)s")
        params["fabric_code"] = f"%{fabric_code}%"

    if name:
        where_clauses.append("f.name ILIKE %(name)s")
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
            cur.execute(f"SELECT COUNT(*) as count FROM fabrics f {where_sql}", params)
            total = cur.fetchone()["count"]

            # Get items with aliases aggregated
            cur.execute(
                f"""
                SELECT f.id, f.fabric_code, f.name, f.image_url, f.gallery,
                       COALESCE(array_agg(fa.alias ORDER BY fa.alias) FILTER (WHERE fa.alias IS NOT NULL), ARRAY[]::text[]) as aliases
                FROM fabrics f
                LEFT JOIN fabric_aliases fa ON f.id = fa.fabric_id
                {where_sql}
                GROUP BY f.id, f.fabric_code, f.name, f.image_url, f.gallery
                ORDER BY f.{sort_by} {sort_dir}
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params
            )
            items = [dict(row) for row in cur.fetchall()]

    return items, total


# ============================================================================
# Variants
# ============================================================================

def create_variant_by_fabric_code(
    fabric_code: str,
    color_code: str,
    finish: str = "Standard",
    gsm: Optional[int] = None,
    width: Optional[int] = None,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None
) -> Optional[dict]:
    """Create a new variant by fabric_code. Returns None if fabric doesn't exist."""
    if gallery is None:
        gallery = {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get fabric by code
            cur.execute("SELECT id FROM fabrics WHERE fabric_code = %s", (fabric_code,))
            fabric = cur.fetchone()
            if not fabric:
                return None

            fabric_id = fabric["id"]

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


def get_variant_by_codes(fabric_code: str, color_code: str) -> Optional[dict]:
    """Get variant by fabric_code and color_code with full details."""
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
                WHERE f.fabric_code = %s AND v.color_code = %s
                """,
                (fabric_code, color_code)
            )
            return cur.fetchone()


def update_variant(
    variant_id: int,
    color_code: Optional[str] = None,
    gsm: Optional[int] = None,
    width: Optional[int] = None,
    finish: Optional[str] = None,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None
) -> Optional[dict]:
    """Update a variant. Returns None if variant doesn't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check variant exists
            cur.execute("SELECT id FROM fabric_variants WHERE id = %s", (variant_id,))
            if not cur.fetchone():
                return None

            # Build dynamic update query
            updates = []
            params = {"id": variant_id}

            if color_code is not None:
                updates.append("color_code = %(color_code)s")
                params["color_code"] = color_code

            if gsm is not None:
                updates.append("gsm = %(gsm)s")
                params["gsm"] = gsm

            if width is not None:
                updates.append("width = %(width)s")
                params["width"] = width

            if finish is not None:
                updates.append("finish = %(finish)s")
                params["finish"] = finish

            if image_url is not None:
                updates.append("image_url = %(image_url)s")
                params["image_url"] = image_url

            if gallery is not None:
                updates.append("gallery = %(gallery)s")
                params["gallery"] = json.dumps(gallery)

            if not updates:
                # No updates provided, just return current variant
                cur.execute(
                    "SELECT id, fabric_id, color_code, gsm, width, finish, image_url, gallery FROM fabric_variants WHERE id = %(id)s",
                    params
                )
                return cur.fetchone()

            update_sql = f"UPDATE fabric_variants SET {', '.join(updates)} WHERE id = %(id)s RETURNING id, fabric_id, color_code, gsm, width, finish, image_url, gallery"
            cur.execute(update_sql, params)
            result = cur.fetchone()
        conn.commit()
        return result


def update_variant_by_codes(
    fabric_code: str,
    color_code: str,
    new_color_code: Optional[str] = None,
    gsm: Optional[int] = None,
    width: Optional[int] = None,
    finish: Optional[str] = None,
    image_url: Optional[str] = None,
    gallery: Optional[dict] = None
) -> Optional[dict]:
    """Update a variant by fabric_code + color_code. Returns None if not found."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Find variant
            cur.execute(
                """
                SELECT v.id FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                WHERE f.fabric_code = %s AND v.color_code = %s
                """,
                (fabric_code, color_code)
            )
            row = cur.fetchone()
            if not row:
                return None

            variant_id = row["id"]

            # Build dynamic update query
            updates = []
            params = {"id": variant_id}

            if new_color_code is not None:
                updates.append("color_code = %(new_color_code)s")
                params["new_color_code"] = new_color_code

            if gsm is not None:
                updates.append("gsm = %(gsm)s")
                params["gsm"] = gsm

            if width is not None:
                updates.append("width = %(width)s")
                params["width"] = width

            if finish is not None:
                updates.append("finish = %(finish)s")
                params["finish"] = finish

            if image_url is not None:
                updates.append("image_url = %(image_url)s")
                params["image_url"] = image_url

            if gallery is not None:
                updates.append("gallery = %(gallery)s")
                params["gallery"] = json.dumps(gallery)

            if not updates:
                # No updates provided, just return current variant detail
                return get_variant_by_codes(fabric_code, color_code)

            update_sql = f"UPDATE fabric_variants SET {', '.join(updates)} WHERE id = %(id)s RETURNING id, fabric_id, color_code, gsm, width, finish, image_url, gallery"
            cur.execute(update_sql, params)
            result = cur.fetchone()
        conn.commit()
        return result


def delete_variant_by_codes(fabric_code: str, color_code: str) -> bool:
    """Delete a variant by fabric_code + color_code. Returns True if deleted."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM fabric_variants v
                USING fabrics f
                WHERE v.fabric_id = f.id AND f.fabric_code = %s AND v.color_code = %s
                RETURNING v.id
                """,
                (fabric_code, color_code)
            )
            result = cur.fetchone()
        conn.commit()
        return result is not None


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
        stock_fields = ", sb.on_hand_m, sb.on_hand_rolls, sb.updated_at"
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

    return items, total


# ============================================================================
# Movements
# ============================================================================

def create_movement_by_codes(
    fabric_code: str,
    color_code: str,
    movement_type: str,
    qty: float,
    uom: str,
    roll_count: Optional[int] = None,
    document_id: Optional[str] = None,
    reason: Optional[str] = None
) -> Optional[dict]:
    """
    Create a movement using fabric_code + color_code.
    Returns None if variant doesn't exist.
    """
    # First lookup the variant
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.id FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                WHERE f.fabric_code = %s AND v.color_code = %s
                """,
                (fabric_code, color_code)
            )
            row = cur.fetchone()
            if not row:
                return None
            variant_id = row["id"]

    # Use existing function
    return create_movement(variant_id, movement_type, qty, uom, roll_count, document_id, reason)


def create_movement(
    variant_id: int,
    movement_type: str,
    qty: float,
    uom: str,
    roll_count: Optional[int] = None,
    document_id: Optional[str] = None,
    reason: Optional[str] = None
) -> Optional[dict]:
    """
    Create a movement and update stock balance.

    Meters are always the source of truth and updated on every movement.
    Rolls are only updated when roll_count is provided.

    Returns dict with movement_id, movement_type, delta_qty_m, on_hand_m_after.
    Returns None if variant doesn't exist.
    """
    # User always provides meters - no conversion needed
    delta_qty_m = Decimal(str(qty))

    # Calculate delta for rolls (can be None)
    delta_rolls = Decimal(str(roll_count)) if roll_count is not None else None

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check variant exists
            cur.execute("SELECT id FROM fabric_variants WHERE id = %s", (variant_id,))
            if not cur.fetchone():
                return None

            # Insert movement
            cur.execute(
                """
                INSERT INTO stock_movements (
                    variant_id, movement_type, delta_qty_m, original_qty, original_uom,
                    roll_count, document_id, reason
                )
                VALUES (
                    %(variant_id)s, %(movement_type)s, %(delta_qty_m)s, %(original_qty)s, %(original_uom)s,
                    %(roll_count)s, %(document_id)s, %(reason)s
                )
                RETURNING id
                """,
                {
                    "variant_id": variant_id,
                    "movement_type": movement_type,
                    "delta_qty_m": delta_qty_m,
                    "original_qty": Decimal(str(qty)),
                    "original_uom": uom,
                    "roll_count": roll_count,
                    "document_id": document_id,
                    "reason": reason
                }
            )
            movement_id = cur.fetchone()["id"]

            # Upsert balance - meters always update, rolls only if provided
            cur.execute(
                """
                INSERT INTO stock_balances (variant_id, on_hand_m, on_hand_rolls, updated_at)
                VALUES (%(variant_id)s, %(delta_qty_m)s, COALESCE(%(delta_rolls)s, 0), now())
                ON CONFLICT (variant_id) DO UPDATE
                SET
                    on_hand_m = stock_balances.on_hand_m + EXCLUDED.on_hand_m,
                    on_hand_rolls = CASE
                        WHEN %(delta_rolls)s IS NOT NULL
                        THEN stock_balances.on_hand_rolls + %(delta_rolls)s
                        ELSE stock_balances.on_hand_rolls
                    END,
                    updated_at = now()
                """,
                {"variant_id": variant_id, "delta_qty_m": delta_qty_m, "delta_rolls": delta_rolls}
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
                    COALESCE(sb.on_hand_rolls, 0) as on_hand_rolls,
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

            return {
                **result,
                "uom": uom
            }


def get_stock_balance_by_codes(fabric_code: str, color_code: str, uom: str = "m") -> Optional[dict]:
    """Get stock balance using fabric_code + color_code."""
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
                    COALESCE(sb.on_hand_rolls, 0) as on_hand_rolls,
                    COALESCE(sb.updated_at, now()) as updated_at
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                LEFT JOIN stock_balances sb ON v.id = sb.variant_id
                WHERE f.fabric_code = %s AND v.color_code = %s
                """,
                (fabric_code, color_code)
            )
            result = cur.fetchone()

            if not result:
                return None

            return {
                **result,
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
                    COALESCE(sb.on_hand_rolls, 0) as on_hand_rolls,
                    COALESCE(sb.updated_at, now()) as updated_at
                FROM fabric_variants v
                JOIN fabrics f ON v.fabric_id = f.id
                LEFT JOIN stock_balances sb ON v.id = sb.variant_id
                WHERE v.id = ANY(%s)
                """,
                (variant_ids,)
            )
            results = cur.fetchall()

            # Add uom to each result
            for result in results:
                result["uom"] = uom

            return results


# ============================================================================
# Unified Search
# ============================================================================

def unified_search(
    q: str,
    include_fabrics: bool = True,
    include_variants: bool = True,
    include_stock: bool = False,
    limit: int = 20
) -> dict:
    """
    Unified search across fabrics (name, code, aliases) and variants.
    Returns { fabrics: [...], variants: [...] }
    """
    result = {"fabrics": [], "variants": []}
    search_pattern = f"%{q}%"

    with get_conn() as conn:
        with conn.cursor() as cur:
            if include_fabrics:
                # Search fabrics with match source indication
                cur.execute(
                    """
                    WITH fabric_matches AS (
                        SELECT DISTINCT ON (f.id)
                            f.id,
                            f.fabric_code,
                            f.name,
                            f.image_url,
                            f.gallery,
                            CASE
                                WHEN f.fabric_code ILIKE %(q)s THEN 'fabric_code'
                                WHEN f.name ILIKE %(q)s THEN 'name'
                                ELSE 'alias'
                            END as match_source
                        FROM fabrics f
                        LEFT JOIN fabric_aliases fa ON f.id = fa.fabric_id
                        WHERE f.fabric_code ILIKE %(q)s
                           OR f.name ILIKE %(q)s
                           OR fa.alias ILIKE %(q)s
                        ORDER BY f.id
                        LIMIT %(limit)s
                    )
                    SELECT fm.*,
                           COALESCE(array_agg(fa.alias ORDER BY fa.alias) FILTER (WHERE fa.alias IS NOT NULL), ARRAY[]::text[]) as aliases
                    FROM fabric_matches fm
                    LEFT JOIN fabric_aliases fa ON fm.id = fa.fabric_id
                    GROUP BY fm.id, fm.fabric_code, fm.name, fm.image_url, fm.gallery, fm.match_source
                    """,
                    {"q": search_pattern, "limit": limit}
                )
                result["fabrics"] = [dict(row) for row in cur.fetchall()]

            if include_variants:
                # Search variants including parent fabric info
                stock_join = "LEFT JOIN stock_balances sb ON v.id = sb.variant_id" if include_stock else ""
                stock_fields = ", sb.on_hand_m, sb.on_hand_rolls, sb.updated_at" if include_stock else ""

                cur.execute(
                    f"""
                    SELECT DISTINCT
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
                    LEFT JOIN fabric_aliases fa ON f.id = fa.fabric_id
                    {stock_join}
                    WHERE v.color_code ILIKE %(q)s
                       OR v.finish ILIKE %(q)s
                       OR f.fabric_code ILIKE %(q)s
                       OR f.name ILIKE %(q)s
                       OR fa.alias ILIKE %(q)s
                    ORDER BY v.id
                    LIMIT %(limit)s
                    """,
                    {"q": search_pattern, "limit": limit}
                )
                result["variants"] = [dict(row) for row in cur.fetchall()]

    return result


# ============================================================================
# Batch Operations
# ============================================================================

def create_variants_batch(
    fabric_code: str,
    variants: list[dict]
) -> tuple[Optional[int], list[dict], list[dict]]:
    """
    Create multiple variants under a single fabric.

    Args:
        fabric_code: The fabric code to create variants under
        variants: List of variant dicts with color_code, finish, gsm, width

    Returns:
        (fabric_id, created_list, failed_list) or (None, [], []) if fabric not found
    """
    created = []
    failed = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get fabric by code
            cur.execute("SELECT id FROM fabrics WHERE fabric_code = %s", (fabric_code,))
            fabric = cur.fetchone()
            if not fabric:
                return None, [], []

            fabric_id = fabric["id"]

            for variant in variants:
                color_code = variant.get("color_code")
                finish = variant.get("finish", "Standard")
                gsm = variant.get("gsm")
                width = variant.get("width")

                try:
                    cur.execute(
                        """
                        INSERT INTO fabric_variants (fabric_id, color_code, gsm, width, finish, image_url, gallery)
                        VALUES (%(fabric_id)s, %(color_code)s, %(gsm)s, %(width)s, %(finish)s, NULL, '{}')
                        RETURNING id, fabric_id, color_code, gsm, width, finish
                        """,
                        {
                            "fabric_id": fabric_id,
                            "color_code": color_code,
                            "gsm": gsm,
                            "width": width,
                            "finish": finish
                        }
                    )
                    result = cur.fetchone()
                    created.append({
                        "fabric_code": fabric_code,
                        "color_code": result["color_code"],
                        "finish": result["finish"]
                    })
                except Exception as e:
                    # Likely UniqueViolation
                    conn.rollback()
                    failed.append({
                        "color_code": color_code,
                        "error": f"Variant with color_code '{color_code}' already exists"
                    })
                    # Need to start a new transaction after rollback
                    continue

        conn.commit()

    return fabric_id, created, failed


def create_movements_batch(
    items: list[dict],
    movement_type: str,
    document_id: Optional[str] = None,
    reason: Optional[str] = None
) -> tuple[list[dict], list[dict]]:
    """
    Create multiple stock movements.

    Args:
        items: List of dicts with fabric_code, color_code, qty, uom, roll_count
        movement_type: RECEIPT or ISSUE
        document_id: Optional document reference
        reason: Optional reason text

    Returns:
        (processed_list, failed_list)
    """
    processed = []
    failed = []

    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in items:
                fabric_code = item.get("fabric_code")
                color_code = item.get("color_code")
                qty = item.get("qty", 0)
                uom = item.get("uom", "m")
                roll_count = item.get("roll_count")

                try:
                    # Look up variant
                    cur.execute(
                        """
                        SELECT v.id FROM fabric_variants v
                        JOIN fabrics f ON v.fabric_id = f.id
                        WHERE f.fabric_code = %s AND v.color_code = %s
                        """,
                        (fabric_code, color_code)
                    )
                    row = cur.fetchone()
                    if not row:
                        failed.append({
                            "fabric_code": fabric_code,
                            "color_code": color_code,
                            "qty": qty,
                            "error": f"Variant '{color_code}' not found for fabric '{fabric_code}'"
                        })
                        continue

                    variant_id = row["id"]

                    # Get previous balance
                    cur.execute(
                        "SELECT COALESCE(on_hand_m, 0) as on_hand_m FROM stock_balances WHERE variant_id = %s",
                        (variant_id,)
                    )
                    balance_row = cur.fetchone()
                    previous_balance = float(balance_row["on_hand_m"]) if balance_row else 0.0

                    # Calculate delta
                    delta_qty_m = Decimal(str(qty))
                    delta_rolls = Decimal(str(roll_count)) if roll_count is not None else None

                    # Insert movement
                    cur.execute(
                        """
                        INSERT INTO stock_movements (
                            variant_id, movement_type, delta_qty_m, original_qty, original_uom,
                            roll_count, document_id, reason
                        )
                        VALUES (
                            %(variant_id)s, %(movement_type)s, %(delta_qty_m)s, %(original_qty)s, %(original_uom)s,
                            %(roll_count)s, %(document_id)s, %(reason)s
                        )
                        RETURNING id
                        """,
                        {
                            "variant_id": variant_id,
                            "movement_type": movement_type,
                            "delta_qty_m": delta_qty_m,
                            "original_qty": Decimal(str(qty)),
                            "original_uom": uom,
                            "roll_count": roll_count,
                            "document_id": document_id,
                            "reason": reason
                        }
                    )
                    movement_id = cur.fetchone()["id"]

                    # Upsert balance
                    cur.execute(
                        """
                        INSERT INTO stock_balances (variant_id, on_hand_m, on_hand_rolls, updated_at)
                        VALUES (%(variant_id)s, %(delta_qty_m)s, COALESCE(%(delta_rolls)s, 0), now())
                        ON CONFLICT (variant_id) DO UPDATE
                        SET
                            on_hand_m = stock_balances.on_hand_m + EXCLUDED.on_hand_m,
                            on_hand_rolls = CASE
                                WHEN %(delta_rolls)s IS NOT NULL
                                THEN stock_balances.on_hand_rolls + %(delta_rolls)s
                                ELSE stock_balances.on_hand_rolls
                            END,
                            updated_at = now()
                        """,
                        {"variant_id": variant_id, "delta_qty_m": delta_qty_m, "delta_rolls": delta_rolls}
                    )

                    # Get new balance
                    cur.execute("SELECT on_hand_m FROM stock_balances WHERE variant_id = %s", (variant_id,))
                    new_balance = float(cur.fetchone()["on_hand_m"])

                    processed.append({
                        "fabric_code": fabric_code,
                        "color_code": color_code,
                        "qty": qty,
                        "previous_balance": previous_balance,
                        "new_balance": new_balance,
                        "movement_id": movement_id
                    })

                except Exception as e:
                    failed.append({
                        "fabric_code": fabric_code,
                        "color_code": color_code,
                        "qty": qty,
                        "error": str(e)
                    })

        conn.commit()

    return processed, failed


def search_variants_batch(
    fabric_code: str,
    color_codes: list[str],
    include_stock: bool = False
) -> tuple[Optional[int], list[dict], list[str]]:
    """
    Search multiple variants by color codes within a fabric.

    Args:
        fabric_code: The fabric code to search within
        color_codes: List of color codes to find
        include_stock: Whether to include stock balances

    Returns:
        (fabric_id, found_list, not_found_list) or (None, [], []) if fabric not found
    """
    if not color_codes:
        return None, [], []

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get fabric by code
            cur.execute("SELECT id FROM fabrics WHERE fabric_code = %s", (fabric_code,))
            fabric = cur.fetchone()
            if not fabric:
                return None, [], color_codes

            fabric_id = fabric["id"]

            # Build query
            stock_join = "LEFT JOIN stock_balances sb ON v.id = sb.variant_id" if include_stock else ""
            stock_fields = ", sb.on_hand_m, sb.on_hand_rolls, sb.updated_at" if include_stock else ""

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
                WHERE f.id = %s AND v.color_code = ANY(%s)
                """,
                (fabric_id, color_codes)
            )
            rows = cur.fetchall()

            # Build found list and track which were found
            found = []
            found_codes = set()

            for row in rows:
                row_dict = dict(row)
                color_code = row_dict["color_code"]
                found_codes.add(color_code)

                # Build variant info
                variant = {
                    "id": row_dict["id"],
                    "fabric_id": row_dict["fabric_id"],
                    "fabric_code": row_dict["fabric_code"],
                    "fabric_name": row_dict["fabric_name"],
                    "fabric_image_url": row_dict.get("fabric_image_url"),
                    "fabric_gallery": row_dict.get("fabric_gallery", {}),
                    "color_code": color_code,
                    "finish": row_dict["finish"],
                    "gsm": row_dict.get("gsm"),
                    "width": row_dict.get("width"),
                    "variant_image_url": row_dict.get("variant_image_url"),
                    "variant_gallery": row_dict.get("variant_gallery", {})
                }

                stock = None
                if include_stock:
                    stock = {
                        "balance": float(row_dict.get("on_hand_m") or 0),
                        "uom": "m"
                    }

                found.append({
                    "color_code": color_code,
                    "variant": variant,
                    "stock": stock
                })

            # Determine not found
            not_found = [cc for cc in color_codes if cc not in found_codes]

    return fabric_id, found, not_found
