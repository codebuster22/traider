"""Repository layer for database operations."""
from datetime import datetime
from typing import Optional
from decimal import Decimal
import json
from traider.db import get_conn


# ============================================================================
# Variant ID Resolution
# ============================================================================

def _resolve_variant_id_on_cursor(
    cur,
    fabric_code: str,
    code_or_alias: str,
) -> Optional[int]:
    """Resolve a primary color_code OR an alias using the caller's cursor.

    Use this from within any function that already holds a transaction — it
    reads the caller's pending writes, which the public wrapper (which opens
    its own pool connection) cannot.
    """
    cur.execute(
        """
        SELECT v.id
          FROM fabric_variants v
          JOIN fabrics f ON v.fabric_id = f.id
         WHERE f.fabric_code = %s AND v.color_code = %s
        """,
        (fabric_code, code_or_alias),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(
        """
        SELECT va.variant_id
          FROM variant_aliases va
          JOIN fabrics f ON va.fabric_id = f.id
         WHERE f.fabric_code = %s AND va.alias = %s
        """,
        (fabric_code, code_or_alias),
    )
    row = cur.fetchone()
    return row["variant_id"] if row else None


def resolve_variant_id(fabric_code: str, code_or_alias: str) -> Optional[int]:
    """Resolve a primary color_code OR an alias to a variant_id within a fabric.

    Single source of truth for fabric_code + color-string → variant_id resolution
    when the caller does not already have an open transaction.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            return _resolve_variant_id_on_cursor(cur, fabric_code, code_or_alias)


class AliasCollisionError(Exception):
    """Raised when an alias would collide with an existing primary color_code or alias in the same fabric."""


def _add_variant_alias_on_cursor(
    cur,
    fabric_id: int,
    variant_id: int,
    alias: str,
) -> bool:
    """Insert an alias row using the caller's cursor. Does not commit/rollback.

    Returns True if inserted, False if (variant_id, alias) already present.
    Raises AliasCollisionError if the alias collides with a primary color_code
    or with an alias pointing at a different variant in the same fabric.

    Callers are responsible for their own transaction management. The reconcile
    writer and _execute_link_on_cursor use this to stay inside one transaction.
    """
    # Invariant 1: alias must not equal any primary color_code in this fabric
    cur.execute(
        "SELECT id FROM fabric_variants WHERE fabric_id = %s AND color_code = %s",
        (fabric_id, alias),
    )
    row = cur.fetchone()
    if row and row["id"] != variant_id:
        raise AliasCollisionError(
            f"Alias '{alias}' collides with primary color_code of variant {row['id']} in fabric_id={fabric_id}"
        )

    # Invariant 2: alias must not already belong to a DIFFERENT variant in this fabric
    cur.execute(
        "SELECT variant_id FROM variant_aliases WHERE fabric_id = %s AND alias = %s",
        (fabric_id, alias),
    )
    row = cur.fetchone()
    if row:
        if row["variant_id"] == variant_id:
            return False  # idempotent no-op
        raise AliasCollisionError(
            f"Alias '{alias}' already belongs to variant {row['variant_id']} in fabric_id={fabric_id}"
        )

    # Safe to insert
    cur.execute(
        "INSERT INTO variant_aliases (fabric_id, variant_id, alias) VALUES (%s, %s, %s)",
        (fabric_id, variant_id, alias),
    )
    return True


def add_variant_alias_direct(fabric_id: int, variant_id: int, alias: str) -> bool:
    """Public wrapper: opens its own connection and commits on success.

    Used by the link route's alias helpers and by test fixtures. The reconcile
    writer and _execute_link call `_add_variant_alias_on_cursor` directly.
    """
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                inserted = _add_variant_alias_on_cursor(cur, fabric_id, variant_id, alias)
            conn.commit()
            return inserted
        except Exception:
            conn.rollback()
            raise


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
                conn.rollback()
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
                result = cur.fetchone()
                conn.rollback()
                return result

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
                conn.rollback()
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
    """Get variant by fabric_code and color_code (alias-aware) with full details."""
    variant_id = resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        return None
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
                conn.rollback()
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
                result = cur.fetchone()
                conn.rollback()
                return result

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
    """Update a variant by fabric_code + color_code (alias-aware). Returns None if not found."""
    variant_id = resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        return None

    return update_variant(
        variant_id=variant_id,
        color_code=new_color_code,
        gsm=gsm,
        width=width,
        finish=finish,
        image_url=image_url,
        gallery=gallery,
    )


def delete_variant_by_codes(fabric_code: str, color_code: str) -> bool:
    """Delete a variant (alias-aware) — removes the underlying variant regardless of which code addresses it."""
    variant_id = resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        return False
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fabric_variants WHERE id = %s", (variant_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


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
            "(v.color_code ILIKE %(q)s OR v.finish ILIKE %(q)s OR f.fabric_code ILIKE %(q)s OR f.name ILIKE %(q)s"
            " OR EXISTS (SELECT 1 FROM variant_aliases va WHERE va.variant_id = v.id AND va.alias ILIKE %(q)s))"
        )
        params["q"] = f"%{q}%"

    if fabric_id:
        where_clauses.append("v.fabric_id = %(fabric_id)s")
        params["fabric_id"] = fabric_id

    if fabric_code:
        where_clauses.append("f.fabric_code ILIKE %(fabric_code)s")
        params["fabric_code"] = f"%{fabric_code}%"

    if color_code:
        where_clauses.append(
            "(v.color_code ILIKE %(color_code)s"
            " OR EXISTS (SELECT 1 FROM variant_aliases va WHERE va.variant_id = v.id AND va.alias ILIKE %(color_code)s))"
        )
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
    Create a movement using fabric_code + color_code (alias-aware).
    Returns None if variant doesn't exist.
    """
    variant_id = resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        return None
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
                conn.rollback()
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


def search_movements(
    fabric_code: Optional[str] = None,
    color_code: Optional[str] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_qty: Optional[float] = None,
    max_qty: Optional[float] = None,
    document_id: Optional[str] = None,
    include_cancelled: bool = False,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "ts",
    sort_dir: str = "desc"
) -> tuple[list[dict], int]:
    """
    Search movement history with optional filters and pagination.

    Args:
        fabric_code: Filter by fabric code (exact match)
        color_code: Filter by color code (exact match)
        movement_type: Filter by type: RECEIPT, ISSUE, ADJUST
        date_from: Movements on or after this date
        date_to: Movements on or before this date
        min_qty: Minimum absolute quantity (filters on ABS(delta_qty_m))
        max_qty: Maximum absolute quantity (filters on ABS(delta_qty_m))
        document_id: Filter by document reference
        include_cancelled: Include cancelled movements (default: false)
        limit: Max results (default: 20)
        offset: Pagination offset
        sort_by: Sort field: ts, delta_qty_m, movement_type
        sort_dir: Sort direction: asc, desc

    Returns:
        (items, total)
    """
    where_clauses = []
    params = {}

    # By default exclude cancelled movements
    if not include_cancelled:
        where_clauses.append("m.is_cancelled = FALSE")

    if fabric_code:
        where_clauses.append("f.fabric_code = %(fabric_code)s")
        params["fabric_code"] = fabric_code

    if color_code:
        where_clauses.append(
            "(v.color_code = %(color_code)s"
            " OR EXISTS (SELECT 1 FROM variant_aliases va WHERE va.variant_id = v.id AND va.alias = %(color_code)s))"
        )
        params["color_code"] = color_code

    if movement_type:
        where_clauses.append("m.movement_type = %(movement_type)s")
        params["movement_type"] = movement_type

    if date_from:
        where_clauses.append("m.ts >= %(date_from)s")
        params["date_from"] = date_from

    if date_to:
        where_clauses.append("m.ts <= %(date_to)s")
        params["date_to"] = date_to

    if min_qty is not None:
        where_clauses.append("ABS(m.delta_qty_m) >= %(min_qty)s")
        params["min_qty"] = min_qty

    if max_qty is not None:
        where_clauses.append("ABS(m.delta_qty_m) <= %(max_qty)s")
        params["max_qty"] = max_qty

    if document_id:
        where_clauses.append("m.document_id = %(document_id)s")
        params["document_id"] = document_id

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Validate and map sort fields
    allowed_sort = {"ts", "delta_qty_m", "movement_type"}
    if sort_by not in allowed_sort:
        sort_by = "ts"
    if sort_dir.lower() not in {"asc", "desc"}:
        sort_dir = "desc"

    sort_map = {
        "ts": "m.ts",
        "delta_qty_m": "m.delta_qty_m",
        "movement_type": "m.movement_type"
    }
    sort_col = sort_map[sort_by]

    params["limit"] = limit
    params["offset"] = offset

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(
                f"""
                SELECT COUNT(*) as count
                FROM stock_movements m
                JOIN fabric_variants v ON m.variant_id = v.id
                JOIN fabrics f ON v.fabric_id = f.id
                {where_sql}
                """,
                params
            )
            total = cur.fetchone()["count"]

            # Get items
            cur.execute(
                f"""
                SELECT
                    m.id,
                    m.ts,
                    f.fabric_code,
                    v.color_code,
                    m.movement_type,
                    m.delta_qty_m,
                    m.original_qty,
                    m.original_uom,
                    m.roll_count,
                    m.document_id,
                    m.reason,
                    m.is_cancelled,
                    m.cancelled_at,
                    m.created_at
                FROM stock_movements m
                JOIN fabric_variants v ON m.variant_id = v.id
                JOIN fabrics f ON v.fabric_id = f.id
                {where_sql}
                ORDER BY {sort_col} {sort_dir}
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params
            )
            items = [dict(row) for row in cur.fetchall()]

    return items, total


def cancel_movement(
    movement_id: int,
    reason: Optional[str] = None
) -> Optional[dict]:
    """
    Cancel a movement and reverse its effect on stock balance.

    Args:
        movement_id: The ID of the movement to cancel
        reason: Optional cancellation reason (appended to existing reason)

    Returns:
        Dict with cancellation details, or None if movement not found.
        Raises ValueError if movement is already cancelled.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Get movement details
            cur.execute(
                """
                SELECT m.id, m.variant_id, m.delta_qty_m, m.roll_count, m.is_cancelled, m.reason
                FROM stock_movements m
                WHERE m.id = %s
                """,
                (movement_id,)
            )
            movement = cur.fetchone()

            if not movement:
                conn.rollback()
                return None

            if movement["is_cancelled"]:
                conn.rollback()
                raise ValueError(f"Movement {movement_id} is already cancelled")

            # Build new reason
            old_reason = movement["reason"] or ""
            if reason:
                new_reason = f"{old_reason} [CANCELLED: {reason}]".strip()
            else:
                new_reason = f"{old_reason} [CANCELLED]".strip()

            # Mark as cancelled
            cur.execute(
                """
                UPDATE stock_movements
                SET is_cancelled = TRUE, cancelled_at = now(), reason = %s
                WHERE id = %s
                RETURNING cancelled_at
                """,
                (new_reason, movement_id)
            )
            cancelled_at = cur.fetchone()["cancelled_at"]

            # Reverse the stock balance
            delta_qty_m = movement["delta_qty_m"]
            roll_count = movement["roll_count"]
            variant_id = movement["variant_id"]

            # Subtract the original delta (reverse the effect)
            cur.execute(
                """
                UPDATE stock_balances
                SET
                    on_hand_m = on_hand_m - %(delta_qty_m)s,
                    on_hand_rolls = on_hand_rolls - COALESCE(%(roll_count)s, 0),
                    updated_at = now()
                WHERE variant_id = %(variant_id)s
                RETURNING on_hand_m
                """,
                {"variant_id": variant_id, "delta_qty_m": delta_qty_m, "roll_count": roll_count}
            )
            balance_row = cur.fetchone()
            new_balance_m = float(balance_row["on_hand_m"]) if balance_row else 0.0

        conn.commit()

        return {
            "message": f"Movement {movement_id} cancelled",
            "movement_id": movement_id,
            "reversed_qty_m": -float(delta_qty_m),
            "new_balance_m": new_balance_m,
            "cancelled_at": cancelled_at
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
    """Get stock balance using fabric_code + color_code (alias-aware)."""
    variant_id = resolve_variant_id(fabric_code, color_code)
    if variant_id is None:
        return None
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
                    WHERE (
                           v.color_code ILIKE %(q)s
                           OR EXISTS (SELECT 1 FROM variant_aliases va WHERE va.variant_id = v.id AND va.alias ILIKE %(q)s)
                          )
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
                    # Look up variant (alias-aware, stays inside the batch's open transaction)
                    variant_id = _resolve_variant_id_on_cursor(cur, fabric_code, color_code)
                    if variant_id is None:
                        failed.append({
                            "fabric_code": fabric_code,
                            "color_code": color_code,
                            "qty": qty,
                            "error": f"Variant '{color_code}' not found for fabric '{fabric_code}'"
                        })
                        continue

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
    include_stock: bool = False,
) -> tuple[Optional[int], list[dict], list[str]]:
    """Search multiple variants by color codes (alias-aware) within a fabric.

    Each item in `found` echoes the input code as `item["color_code"]` and
    the resolved variant's primary as `item["variant"]["color_code"]`.

    Returns:
        (fabric_id, found_list, not_found_list) or (None, [], color_codes) if fabric not found
    """
    if not color_codes:
        return (None, [], [])

    fabric = get_fabric_by_code(fabric_code)
    if fabric is None:
        return (None, [], list(color_codes))

    found: list[dict] = []
    not_found: list[str] = []
    for code in color_codes:
        variant_id = resolve_variant_id(fabric_code, code)
        if variant_id is None:
            not_found.append(code)
            continue
        variant = get_variant_detail(variant_id)
        if variant is None:
            not_found.append(code)
            continue

        stock = None
        if include_stock:
            bal = get_stock_balance(variant_id, uom="m")
            stock = {
                "balance": float(bal["on_hand_m"]) if bal else 0.0,
                "uom": "m",
            }

        found.append({
            "color_code": code,      # echoes the input (may be primary OR alias)
            "variant": variant,      # resolved variant, whose color_code is the primary
            "stock": stock,
        })

    return (fabric["id"], found, not_found)


# ============================================================================
# Variant alias listing and link algorithm
# ============================================================================

def list_variant_aliases(variant_id: int) -> list[str]:
    """Return all aliases for a variant, sorted."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT alias FROM variant_aliases WHERE variant_id = %s ORDER BY alias",
                (variant_id,),
            )
            return [row["alias"] for row in cur.fetchall()]


def _execute_link_on_cursor(
    cur,
    fabric_id: int,
    fabric_code: str,
    color_codes: list[str],
    confirm: bool = False,
) -> dict:
    """Execute the link algorithm against an open cursor. See spec §6.3.

    Does NOT open a connection, does NOT commit, does NOT rollback. Callers
    own transaction management. Returns one of:
      - {"result": "not_found"}
      - {"result": "linked", "primary": ..., "aliases_added": [...],
         "merged_from": [...], "final_on_hand_m": ...}
      - {"result": "already_linked", "primary": ...}
      - {"result": "confirmation_required", "plan": {...}, "message": ...}

    Note: when returning confirmation_required, the caller should roll back
    (no writes have happened before that point, but the SET TRANSACTION that
    may have been issued needs cleaning up).
    """
    if not color_codes:
        return {"result": "not_found"}

    # Step 1: resolve each code to a variant_id (or None). Use the cursor-aware
    # resolver so we see the caller's pending writes.
    resolved = [
        (c, _resolve_variant_id_on_cursor(cur, fabric_code, c))
        for c in color_codes
    ]
    distinct_vids = list({vid for _, vid in resolved if vid is not None})

    if not distinct_vids:
        return {"result": "not_found"}

    # Step 3: determine survivor
    primary_code = color_codes[0]
    primary_vid = resolved[0][1]
    needs_promote_swap = False
    needs_rename = False
    old_primary_to_demote: Optional[str] = None
    survivor_id: int

    if primary_vid is not None:
        survivor_id = primary_vid
        cur.execute(
            "SELECT color_code FROM fabric_variants WHERE id = %s",
            (survivor_id,),
        )
        current_primary = cur.fetchone()["color_code"]
        if current_primary != primary_code:
            needs_promote_swap = True
            old_primary_to_demote = current_primary
    else:
        first_resolving = next(vid for _, vid in resolved if vid is not None)
        survivor_id = first_resolving
        needs_rename = True
        cur.execute(
            "SELECT color_code FROM fabric_variants WHERE id = %s",
            (survivor_id,),
        )
        old_primary_to_demote = cur.fetchone()["color_code"]

    # Step 4: merge sources
    merge_source_ids = [vid for vid in distinct_vids if vid != survivor_id]

    # Step 5: stock check for confirmation
    sources_with_stock = []
    for src_id in merge_source_ids:
        cur.execute(
            """
            SELECT
                COALESCE(sb.on_hand_m, 0) AS on_hand_m,
                (SELECT COUNT(*) FROM stock_movements sm
                  WHERE sm.variant_id = v.id AND sm.is_cancelled = false) AS movement_count,
                v.color_code
              FROM fabric_variants v
              LEFT JOIN stock_balances sb ON sb.variant_id = v.id
             WHERE v.id = %s
            """,
            (src_id,),
        )
        row = cur.fetchone()
        if row and (float(row["on_hand_m"] or 0) > 0 or row["movement_count"] > 0):
            sources_with_stock.append({
                "color_code": row["color_code"],
                "on_hand_m": float(row["on_hand_m"] or 0),
                "movement_count": int(row["movement_count"]),
            })

    if sources_with_stock and not confirm:
        cur.execute(
            "SELECT COALESCE(on_hand_m, 0) AS on_hand_m FROM stock_balances WHERE variant_id = %s",
            (survivor_id,),
        )
        row = cur.fetchone()
        survivor_balance = float(row["on_hand_m"] or 0) if row else 0.0
        result_total = survivor_balance + sum(s["on_hand_m"] for s in sources_with_stock)
        # Do NOT rollback here — the caller owns transaction management.
        return {
            "result": "confirmation_required",
            "plan": {
                "primary": primary_code,
                "merge_sources": sources_with_stock,
                "result_on_hand_m": result_total,
            },
            "message": (
                f"Linking will merge {len(sources_with_stock)} variant(s) with existing stock. "
                "This cannot be undone. Resend with confirm=true to proceed."
            ),
        }

    # Step 3 continued: apply promote-swap or rename (uses _add_variant_alias_on_cursor)
    if needs_promote_swap:
        cur.execute(
            "DELETE FROM variant_aliases WHERE fabric_id = %s AND alias = %s",
            (fabric_id, primary_code),
        )
        cur.execute(
            "UPDATE fabric_variants SET color_code = %s WHERE id = %s",
            (primary_code, survivor_id),
        )
        _add_variant_alias_on_cursor(cur, fabric_id, survivor_id, old_primary_to_demote)
    elif needs_rename:
        cur.execute(
            "UPDATE fabric_variants SET color_code = %s WHERE id = %s",
            (primary_code, survivor_id),
        )
        _add_variant_alias_on_cursor(cur, fabric_id, survivor_id, old_primary_to_demote)

    # Step 6: merge each source into survivor
    merged_from = []
    for src_id in merge_source_ids:
        cur.execute(
            "SELECT color_code FROM fabric_variants WHERE id = %s",
            (src_id,),
        )
        src_row = cur.fetchone()
        if src_row is None:
            continue
        src_primary = src_row["color_code"]
        merged_from.append(src_primary)

        cur.execute(
            "UPDATE stock_movements SET variant_id = %s WHERE variant_id = %s",
            (survivor_id, src_id),
        )
        cur.execute(
            """
            INSERT INTO variant_aliases (fabric_id, variant_id, alias)
            SELECT fabric_id, %s, alias FROM variant_aliases WHERE variant_id = %s
            ON CONFLICT DO NOTHING
            """,
            (survivor_id, src_id),
        )
        cur.execute("DELETE FROM variant_aliases WHERE variant_id = %s", (src_id,))
        cur.execute(
            """
            INSERT INTO variant_aliases (fabric_id, variant_id, alias)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (fabric_id, survivor_id, src_primary),
        )
        cur.execute("DELETE FROM stock_balances WHERE variant_id = %s", (src_id,))
        cur.execute("DELETE FROM fabric_variants WHERE id = %s", (src_id,))

    # Step 7: add unresolved codes as aliases
    aliases_added = []
    unresolved_inputs = [
        c for c, vid in resolved
        if vid is None and c != primary_code
    ]
    for c in unresolved_inputs:
        added = _add_variant_alias_on_cursor(cur, fabric_id, survivor_id, c)
        if added:
            aliases_added.append(c)

    # Step 8: recompute survivor balance
    cur.execute(
        """
        INSERT INTO stock_balances (variant_id, on_hand_m, on_hand_rolls, updated_at)
        VALUES (%s, 0, 0, now())
        ON CONFLICT (variant_id) DO NOTHING
        """,
        (survivor_id,),
    )
    cur.execute(
        """
        UPDATE stock_balances sb
           SET on_hand_m = COALESCE((
                 SELECT SUM(delta_qty_m) FROM stock_movements
                  WHERE variant_id = sb.variant_id AND is_cancelled = false
               ), 0),
               on_hand_rolls = COALESCE((
                 SELECT SUM(COALESCE(roll_count, 0)) FROM stock_movements
                  WHERE variant_id = sb.variant_id AND is_cancelled = false
               ), 0),
               updated_at = now()
         WHERE variant_id = %s
        """,
        (survivor_id,),
    )
    cur.execute(
        "SELECT on_hand_m FROM stock_balances WHERE variant_id = %s",
        (survivor_id,),
    )
    final_row = cur.fetchone()
    final_on_hand = float(final_row["on_hand_m"]) if final_row else 0.0

    if not aliases_added and not merged_from and not needs_promote_swap and not needs_rename:
        return {"result": "already_linked", "primary": primary_code}

    return {
        "result": "linked",
        "primary": primary_code,
        "aliases_added": aliases_added,
        "merged_from": merged_from,
        "final_on_hand_m": final_on_hand,
    }


def _execute_link(
    fabric_code: str,
    color_codes: list[str],
    confirm: bool = False,
) -> dict:
    """Public wrapper: opens its own SERIALIZABLE transaction and calls the inner helper.

    Used by the REST route (Task C.3). The reconcile writer (Task H.1) calls
    _execute_link_on_cursor directly from inside its own transaction.
    """
    if not color_codes:
        return {"result": "not_found"}

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cur.execute("SELECT id FROM fabrics WHERE fabric_code = %s", (fabric_code,))
                fabric_row = cur.fetchone()
                if fabric_row is None:
                    conn.rollback()
                    return {"result": "not_found"}
                fabric_id = fabric_row["id"]
                result = _execute_link_on_cursor(
                    cur, fabric_id, fabric_code, color_codes, confirm
                )
            if result["result"] == "confirmation_required":
                conn.rollback()
            else:
                conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
