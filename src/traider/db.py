"""Database connection and initialization."""
import os
from contextlib import contextmanager
from typing import Generator
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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
"""


def init_db() -> None:
    """Initialize database: create tables and indexes."""
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
