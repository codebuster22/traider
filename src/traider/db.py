"""Database connection and initialization."""
import logging
import os
import re
from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/inventory")

# Global connection pool
_pool: ConnectionPool | None = None


DDL = """
-- Fuzzy search helpers
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS fabrics (
  id BIGSERIAL PRIMARY KEY,
  fabric_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS fabric_aliases (
  fabric_id BIGINT NOT NULL REFERENCES fabrics(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  PRIMARY KEY (fabric_id, alias)
);

CREATE TABLE IF NOT EXISTS fabric_variants (
  id BIGSERIAL PRIMARY KEY,
  fabric_id BIGINT NOT NULL REFERENCES fabrics(id) ON DELETE CASCADE,
  color_code TEXT NOT NULL,
  finish TEXT NOT NULL DEFAULT 'Standard',
  gsm INT,
  width INT,
  image_url TEXT,
  UNIQUE (fabric_id, color_code)
);

-- Source of truth for changes (always meters)
CREATE TABLE IF NOT EXISTS stock_movements (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  variant_id BIGINT NOT NULL REFERENCES fabric_variants(id) ON DELETE CASCADE,
  movement_type TEXT NOT NULL CHECK (movement_type IN ('RECEIPT','ISSUE','ADJUST')),
  delta_qty_m NUMERIC(14,3) NOT NULL,
  original_qty NUMERIC(14,3) NOT NULL,
  original_uom TEXT NOT NULL CHECK (original_uom IN ('m','roll')),
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast answer per variant
CREATE TABLE IF NOT EXISTS stock_balances (
  variant_id BIGINT PRIMARY KEY REFERENCES fabric_variants(id) ON DELETE CASCADE,
  on_hand_m NUMERIC(14,3) NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for search and performance
CREATE INDEX IF NOT EXISTS idx_fabrics_code_trgm
  ON fabrics USING gin (fabric_code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_fabrics_name_trgm
  ON fabrics USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_fabric_aliases_trgm
  ON fabric_aliases USING gin (alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_variants_fabric_color
  ON fabric_variants (fabric_id, color_code);
CREATE INDEX IF NOT EXISTS idx_variants_color_trgm
  ON fabric_variants USING gin (color_code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_variants_finish_trgm
  ON fabric_variants USING gin (finish gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_variants_gsm
  ON fabric_variants (gsm);
CREATE INDEX IF NOT EXISTS idx_variants_width
  ON fabric_variants (width);
CREATE INDEX IF NOT EXISTS idx_movements_variant_ts
  ON stock_movements (variant_id, ts DESC);

-- Migration: Add gallery column for structured image galleries
ALTER TABLE fabrics
  ADD COLUMN IF NOT EXISTS gallery JSONB DEFAULT '{}'::jsonb;

ALTER TABLE fabric_variants
  ADD COLUMN IF NOT EXISTS gallery JSONB DEFAULT '{}'::jsonb;

-- Migration: Add roll_count and document_id tracking to movements
ALTER TABLE stock_movements
  ADD COLUMN IF NOT EXISTS roll_count INT NULL;

ALTER TABLE stock_movements
  ADD COLUMN IF NOT EXISTS document_id TEXT NULL;

-- Migration: Add roll tracking to stock balances
ALTER TABLE stock_balances
  ADD COLUMN IF NOT EXISTS on_hand_rolls NUMERIC(14,3) DEFAULT 0;

-- Migration: Add soft delete columns for movements
ALTER TABLE stock_movements
  ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE stock_movements
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ NULL;

-- Migration tracking table
CREATE TABLE IF NOT EXISTS migrations (
  name TEXT PRIMARY KEY,
  completed_at TIMESTAMPTZ DEFAULT now()
);
"""


# --------------------------------------------------------------------------
# Data Sanitization Functions
# --------------------------------------------------------------------------

def sanitize_fabric_code(code: str) -> str:
    """Sanitize fabric_code: UPPERCASE, underscores, alphanumeric only.

    Steps:
    1. Convert to UPPERCASE
    2. Replace whitespace and dashes with underscore (_)
    3. Remove all characters except A-Z, 0-9, _
    4. Collapse multiple underscores (__ → _)
    5. Trim leading/trailing underscores
    """
    result = code.upper()
    result = re.sub(r'[\s\-]+', '_', result)
    result = re.sub(r'[^A-Z0-9_]', '', result)
    result = re.sub(r'_+', '_', result)
    result = result.strip('_')
    return result


def sanitize_color_code(code: str) -> str:
    """Sanitize color_code: UPPERCASE, alphanumeric only.

    Steps:
    1. Convert to UPPERCASE
    2. Remove ALL characters except A-Z, 0-9
    """
    result = code.upper()
    result = re.sub(r'[^A-Z0-9]', '', result)
    return result


def _sanitize_fabric_codes(cur: psycopg.Cursor) -> int:
    """Sanitize all fabric codes. Returns count of updated fabrics."""
    cur.execute("SELECT id, fabric_code FROM fabrics")
    fabrics = cur.fetchall()

    updated = 0
    conflicts = []

    for fabric in fabrics:
        old_code = fabric['fabric_code']
        new_code = sanitize_fabric_code(old_code)

        if new_code == old_code:
            continue  # No change needed

        # Check for conflict
        cur.execute("SELECT 1 FROM fabrics WHERE fabric_code = %s AND id != %s", (new_code, fabric['id']))
        if cur.fetchone():
            conflicts.append(f"{old_code} → {new_code}")
            continue

        # Update fabric code
        cur.execute("UPDATE fabrics SET fabric_code = %s WHERE id = %s", (new_code, fabric['id']))
        logger.info(f"Sanitized fabric code: {old_code} → {new_code}")
        updated += 1

    if conflicts:
        logger.warning(f"Fabric code conflicts (skipped): {conflicts}")

    return updated


def _sanitize_color_codes(cur: psycopg.Cursor) -> int:
    """Sanitize all color codes. Returns count of updated variants."""
    cur.execute("""
        SELECT v.id, v.fabric_id, v.color_code, f.fabric_code
        FROM fabric_variants v
        JOIN fabrics f ON f.id = v.fabric_id
    """)
    variants = cur.fetchall()

    updated = 0
    conflicts = []

    for variant in variants:
        old_code = variant['color_code']
        new_code = sanitize_color_code(old_code)

        if new_code == old_code:
            continue  # No change needed

        # Check for conflict within same fabric
        cur.execute(
            "SELECT 1 FROM fabric_variants WHERE fabric_id = %s AND color_code = %s AND id != %s",
            (variant['fabric_id'], new_code, variant['id'])
        )
        if cur.fetchone():
            conflicts.append(f"{variant['fabric_code']}/{old_code} → {new_code}")
            continue

        # Update color code
        cur.execute("UPDATE fabric_variants SET color_code = %s WHERE id = %s", (new_code, variant['id']))
        logger.info(f"Sanitized color code: {variant['fabric_code']}/{old_code} → {new_code}")
        updated += 1

    if conflicts:
        logger.warning(f"Color code conflicts (skipped): {conflicts}")

    return updated


def _delete_corrupted_movements(cur: psycopg.Cursor) -> int:
    """Delete all movements from January 15, 2026. Returns count deleted."""
    cur.execute("""
        DELETE FROM stock_movements
        WHERE created_at::date = '2026-01-15'
        RETURNING id
    """)
    deleted = cur.rowcount
    if deleted > 0:
        logger.info(f"Deleted {deleted} corrupted movements from 2026-01-15")
    return deleted


def _recalculate_balances(cur: psycopg.Cursor) -> None:
    """Recalculate all stock balances from non-cancelled movements."""
    # Reset all balances to zero
    cur.execute("UPDATE stock_balances SET on_hand_m = 0, on_hand_rolls = 0, updated_at = now()")

    # Recalculate from non-cancelled movements
    cur.execute("""
        UPDATE stock_balances sb
        SET
            on_hand_m = COALESCE(agg.total_m, 0),
            on_hand_rolls = COALESCE(agg.total_rolls, 0),
            updated_at = now()
        FROM (
            SELECT
                variant_id,
                SUM(delta_qty_m) as total_m,
                SUM(COALESCE(roll_count, 0)) as total_rolls
            FROM stock_movements
            WHERE is_cancelled = FALSE
            GROUP BY variant_id
        ) agg
        WHERE sb.variant_id = agg.variant_id
    """)
    logger.info("Recalculated all stock balances from movements")


def run_migrations(conn: psycopg.Connection) -> None:
    """Run one-time data migrations."""
    with conn.cursor() as cur:
        # Check if already run
        cur.execute("SELECT 1 FROM migrations WHERE name = 'sanitize_codes_cleanup_v1'")
        if cur.fetchone():
            return  # Already completed

        logger.info("Running migration: sanitize_codes_cleanup_v1")

        # Part A: Sanitize fabric codes
        fabric_count = _sanitize_fabric_codes(cur)
        logger.info(f"Part A complete: {fabric_count} fabric codes sanitized")

        # Part B: Sanitize color codes
        color_count = _sanitize_color_codes(cur)
        logger.info(f"Part B complete: {color_count} color codes sanitized")

        # Part C: Delete corrupted movements
        deleted_count = _delete_corrupted_movements(cur)
        logger.info(f"Part C complete: {deleted_count} movements deleted")

        # Part D: Recalculate balances
        _recalculate_balances(cur)
        logger.info("Part D complete: balances recalculated")

        # Mark complete
        cur.execute("INSERT INTO migrations (name) VALUES ('sanitize_codes_cleanup_v1')")
        conn.commit()
        logger.info("Migration sanitize_codes_cleanup_v1 completed successfully")

    # Run targeted color code fixes
    _run_targeted_color_fixes(conn)


def _run_targeted_color_fixes(conn: psycopg.Connection) -> None:
    """
    Targeted one-time fixes for PV_COZIRA_MUL fabric (id=2):
    1. Merge '901 (A)' into '901A' - move movements, delete old variant
    2. Rename '905 B' to '905B'

    DELETE THIS FUNCTION AFTER MIGRATION COMPLETES.
    """
    with conn.cursor() as cur:
        # Check if already run
        cur.execute("SELECT 1 FROM migrations WHERE name = 'targeted_color_fixes_v1'")
        if cur.fetchone():
            return  # Already completed

        logger.info("Running migration: targeted_color_fixes_v1")
        fabric_id = 2  # PV_COZIRA_MUL

        # -----------------------------------------------------------------
        # Fix 1: Merge '901 (A)' into '901A'
        # -----------------------------------------------------------------
        cur.execute(
            "SELECT id FROM fabric_variants WHERE fabric_id = %s AND color_code = %s",
            (fabric_id, '901A')
        )
        target_row = cur.fetchone()

        cur.execute(
            "SELECT id FROM fabric_variants WHERE fabric_id = %s AND color_code = %s",
            (fabric_id, '901 (A)')
        )
        source_row = cur.fetchone()

        if target_row and source_row:
            target_id = target_row['id']
            source_id = source_row['id']

            # Move all stock movements from source to target
            cur.execute(
                "UPDATE stock_movements SET variant_id = %s WHERE variant_id = %s",
                (target_id, source_id)
            )
            moved_count = cur.rowcount
            logger.info(f"Moved {moved_count} movements from '901 (A)' to '901A'")

            # Delete source variant's stock balance (if exists)
            cur.execute("DELETE FROM stock_balances WHERE variant_id = %s", (source_id,))

            # Delete source variant
            cur.execute("DELETE FROM fabric_variants WHERE id = %s", (source_id,))
            logger.info("Deleted variant '901 (A)'")

            # Recalculate target variant's balance
            cur.execute("""
                INSERT INTO stock_balances (variant_id, on_hand_m, on_hand_rolls, updated_at)
                SELECT
                    %(variant_id)s,
                    COALESCE(SUM(delta_qty_m), 0),
                    COALESCE(SUM(COALESCE(roll_count, 0)), 0),
                    now()
                FROM stock_movements
                WHERE variant_id = %(variant_id)s AND is_cancelled = FALSE
                ON CONFLICT (variant_id) DO UPDATE
                SET
                    on_hand_m = EXCLUDED.on_hand_m,
                    on_hand_rolls = EXCLUDED.on_hand_rolls,
                    updated_at = now()
            """, {"variant_id": target_id})
            logger.info("Recalculated balance for '901A'")
        else:
            if not target_row:
                logger.warning("Target variant '901A' not found - skipping merge")
            if not source_row:
                logger.warning("Source variant '901 (A)' not found - skipping merge")

        # -----------------------------------------------------------------
        # Fix 2: Rename '05B' to '905B' (missing leading 9)
        # -----------------------------------------------------------------
        cur.execute(
            "UPDATE fabric_variants SET color_code = %s WHERE fabric_id = %s AND color_code = %s",
            ('905B', fabric_id, '05B')
        )
        if cur.rowcount > 0:
            logger.info("Renamed '05B' to '905B'")
        else:
            logger.warning("Variant '05B' not found - skipping rename")

        # Mark complete
        cur.execute("INSERT INTO migrations (name) VALUES ('targeted_color_fixes_v1')")
        conn.commit()
        logger.info("Migration targeted_color_fixes_v1 completed successfully")


def init_db() -> None:
    """Initialize database: create tables and indexes, run migrations."""
    global _pool

    # Create connection pool
    _pool = ConnectionPool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row}
    )

    # Run DDL
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()

        # Run data migrations
        run_migrations(conn)


def close_db() -> None:
    """Close database connection pool."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    """Get a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor() -> Generator[psycopg.Cursor, None, None]:
    """Get a cursor from a pooled connection."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur
