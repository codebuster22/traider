# Plan: Tone (Batch) and Godown Tracking

## Problem Statement

### 1. Tone/Batch Tracking
Same fabric variant (e.g., variant ID 991) can arrive in multiple batches with slight tone differences due to dyeing variations. Currently handled manually by adding letter suffixes to color codes (991A, 991B).

**Business Rule:** Orders must be fulfilled from a single tone - cannot mix 500m from tone A with 100m from tone B for a 600m order.

### 2. Godown (Warehouse) Tracking
Need to track which godown/warehouse fabric is stored in. Should support a default godown for simple single-warehouse scenarios.

---

## Design Decision: Tone vs. New Variant

### Option A: Create New Variants per Tone (NOT recommended)
- Treat 991A and 991B as completely separate variants
- Simple but causes variant proliferation
- Loses the semantic meaning that they're the SAME fabric with different dye batches

### Option B: Introduce Tone/Batch as Sub-division of Variant (RECOMMENDED)
- Variant 991 remains one entity (same specs: color_code, gsm, width, finish)
- Tones (A, B, C) are tracked as sub-divisions of stock
- Stock tracked at `(variant_id, tone_id)` level
- Preserves the relationship: "These are the same fabric, different dye batches"

**Recommendation: Option B** - Aligns with textile industry practices where batch tracking is essential.

---

## Proposed Data Model

### New Tables

#### 1. `godowns` (Warehouses)
```sql
CREATE TABLE IF NOT EXISTS godowns (
    id          BIGSERIAL PRIMARY KEY,
    code        TEXT UNIQUE NOT NULL,        -- e.g., "GD-01", "MAIN"
    name        TEXT NOT NULL,               -- e.g., "Main Godown", "Cold Storage"
    address     TEXT,
    is_default  BOOLEAN DEFAULT FALSE,       -- Only one can be default
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Ensure only one default godown
CREATE UNIQUE INDEX idx_godowns_single_default
ON godowns (is_default) WHERE is_default = TRUE;
```

#### 2. `tones` (Batch/Tone Registry)
```sql
CREATE TABLE IF NOT EXISTS tones (
    id          BIGSERIAL PRIMARY KEY,
    variant_id  BIGINT NOT NULL REFERENCES fabric_variants(id) ON DELETE CASCADE,
    suffix      TEXT NOT NULL,               -- e.g., "A", "B", "C" or "01", "02"
    description TEXT,                        -- Optional: "Slightly darker", "Feb 2024 batch"
    received_at TIMESTAMPTZ DEFAULT now(),   -- When this tone was first received
    is_active   BOOLEAN DEFAULT TRUE,        -- Soft delete for depleted tones
    created_at  TIMESTAMPTZ DEFAULT now(),

    UNIQUE(variant_id, suffix)               -- 991-A, 991-B must be unique
);

CREATE INDEX idx_tones_variant ON tones(variant_id);
```

### Modified Tables

#### 3. `stock_balances` - New Composite Key
```sql
-- Current: PRIMARY KEY (variant_id)
-- New: PRIMARY KEY (variant_id, tone_id, godown_id)

-- Migration approach: Create new table, migrate data
CREATE TABLE IF NOT EXISTS stock_balances_v2 (
    variant_id   BIGINT NOT NULL REFERENCES fabric_variants(id) ON DELETE CASCADE,
    tone_id      BIGINT REFERENCES tones(id) ON DELETE CASCADE,  -- NULL = unspecified tone (legacy)
    godown_id    BIGINT REFERENCES godowns(id) ON DELETE RESTRICT,  -- NULL = default godown
    on_hand_m    NUMERIC(14,3) DEFAULT 0,
    on_hand_rolls NUMERIC(14,3) DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (variant_id, COALESCE(tone_id, 0), COALESCE(godown_id, 0))
);

CREATE INDEX idx_stock_balances_v2_variant ON stock_balances_v2(variant_id);
CREATE INDEX idx_stock_balances_v2_godown ON stock_balances_v2(godown_id);
CREATE INDEX idx_stock_balances_v2_tone ON stock_balances_v2(tone_id);
```

#### 4. `stock_movements` - Add Tracking Fields
```sql
-- Add new columns (non-breaking)
ALTER TABLE stock_movements
ADD COLUMN tone_id BIGINT REFERENCES tones(id) ON DELETE SET NULL,
ADD COLUMN godown_id BIGINT REFERENCES godowns(id) ON DELETE SET NULL,
ADD COLUMN transfer_to_godown_id BIGINT REFERENCES godowns(id) ON DELETE SET NULL;

-- Index for efficient queries
CREATE INDEX idx_movements_tone ON stock_movements(tone_id);
CREATE INDEX idx_movements_godown ON stock_movements(godown_id);
```

---

## Display Format

### Variant + Tone Display
```
Variant: 991 (Cotton Jersey, Red, 180gsm, 60")
  ├── Tone A: 500m (Main Godown)
  ├── Tone B: 200m (Main Godown)
  └── Total: 700m

# When searching/displaying, show as:
991A - Cotton Jersey Red 180gsm 60" - 500m (Main Godown)
991B - Cotton Jersey Red 180gsm 60" - 200m (Main Godown)
```

### API Response Enhancement
```json
{
  "variant_id": 991,
  "fabric_code": "CTN-JRS",
  "color_code": "RED-01",
  "tones": [
    {
      "tone_id": 1,
      "suffix": "A",
      "display_code": "991A",
      "on_hand_m": 500,
      "godown": "Main Godown"
    },
    {
      "tone_id": 2,
      "suffix": "B",
      "display_code": "991B",
      "on_hand_m": 200,
      "godown": "Main Godown"
    }
  ],
  "total_on_hand_m": 700
}
```

---

## Movement Types Enhancement

### Current Movement Types
- RECEIPT - Stock in
- ISSUE - Stock out
- ADJUST - Corrections

### New Movement Type (Optional)
- **TRANSFER** - Move stock between godowns

```sql
-- Transfer movement example: Move 100m from Godown 1 to Godown 2
-- Creates TWO movements:
-- 1. TRANSFER (negative) from source godown
-- 2. TRANSFER (positive) to destination godown
-- Both linked by document_id for traceability
```

---

## API Changes

### New Endpoints

#### Godowns
```
POST   /godowns              - Create godown
PUT    /godowns/{id}         - Update godown
GET    /godowns              - List all godowns
DELETE /godowns/{id}         - Soft delete (set is_active=false)
PUT    /godowns/{id}/default - Set as default godown
```

#### Tones
```
POST   /tones                - Create tone for a variant
PUT    /tones/{id}           - Update tone description
GET    /variants/{id}/tones  - List all tones for a variant
DELETE /tones/{id}           - Soft delete (set is_active=false)
```

#### Transfers (Optional)
```
POST   /transfer             - Transfer stock between godowns
```

### Modified Endpoints

#### Stock Movements (`/receive`, `/issue`, `/adjust`)
```python
# Current
class MovementCreate(BaseModel):
    variant_id: int
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int]
    document_id: Optional[str]
    reason: Optional[str]

# Enhanced
class MovementCreate(BaseModel):
    variant_id: int
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int]
    document_id: Optional[str]
    reason: Optional[str]
    # New fields
    tone_id: Optional[int] = None       # If None, auto-create new tone on RECEIPT
    tone_suffix: Optional[str] = None   # Alternative: specify suffix, system creates tone
    godown_id: Optional[int] = None     # If None, use default godown
```

#### Receive Stock - Tone Handling
```python
# Scenario 1: Explicit tone
POST /receive
{
    "variant_id": 991,
    "qty": 500,
    "uom": "m",
    "tone_id": 1  # Existing tone A
}

# Scenario 2: Create new tone
POST /receive
{
    "variant_id": 991,
    "qty": 200,
    "uom": "m",
    "tone_suffix": "B",  # Creates tone B if doesn't exist
    "reason": "New batch, slightly darker"
}

# Scenario 3: Auto-increment tone (optional convenience)
POST /receive
{
    "variant_id": 991,
    "qty": 300,
    "uom": "m",
    "auto_tone": true  # Creates next available suffix (C)
}
```

#### Issue Stock - Tone Requirement
```python
# MUST specify tone_id for issues (enforces single-tone fulfillment)
POST /issue
{
    "variant_id": 991,
    "qty": 400,
    "uom": "m",
    "tone_id": 1,  # REQUIRED - from which tone to issue
    "godown_id": 1,
    "document_id": "INV-2024-001"
}

# Error if tone_id not specified:
# {"error": "tone_id is required for stock issue to ensure single-tone fulfillment"}
```

#### Stock Query - Enhanced Response
```python
GET /stock?variant_id=991

# Response includes tone breakdown
{
    "variant_id": 991,
    "fabric_code": "CTN-JRS",
    "color_code": "RED-01",
    "stock_by_tone": [
        {
            "tone_id": 1,
            "tone_suffix": "A",
            "display_code": "991A",
            "stock_by_godown": [
                {"godown_id": 1, "godown_name": "Main", "on_hand_m": 300},
                {"godown_id": 2, "godown_name": "Backup", "on_hand_m": 200}
            ],
            "total_on_hand_m": 500
        },
        {
            "tone_id": 2,
            "tone_suffix": "B",
            "display_code": "991B",
            "stock_by_godown": [
                {"godown_id": 1, "godown_name": "Main", "on_hand_m": 200}
            ],
            "total_on_hand_m": 200
        }
    ],
    "total_on_hand_m": 700
}

# Simplified query (aggregate view)
GET /stock?variant_id=991&aggregate=true
{
    "variant_id": 991,
    "on_hand_m": 700,
    "on_hand_rolls": 3.5
}
```

---

## Migration Strategy

### Phase 1: Database Schema (Non-breaking)
1. Create `godowns` table
2. Create `tones` table
3. Add new columns to `stock_movements` (nullable)
4. Create `stock_balances_v2` table

### Phase 2: Default Data Setup
1. Create default godown: `{"code": "DEFAULT", "name": "Default Godown", "is_default": true}`
2. For existing stock, create "LEGACY" tone entries

### Phase 3: Data Migration
```sql
-- For each existing variant with stock, create a legacy tone
INSERT INTO tones (variant_id, suffix, description)
SELECT DISTINCT variant_id, 'LEGACY', 'Pre-migration stock'
FROM stock_balances
WHERE on_hand_m > 0;

-- Migrate balances to new table
INSERT INTO stock_balances_v2 (variant_id, tone_id, godown_id, on_hand_m, on_hand_rolls, updated_at)
SELECT
    sb.variant_id,
    t.id as tone_id,
    (SELECT id FROM godowns WHERE is_default = TRUE) as godown_id,
    sb.on_hand_m,
    sb.on_hand_rolls,
    sb.updated_at
FROM stock_balances sb
JOIN tones t ON t.variant_id = sb.variant_id AND t.suffix = 'LEGACY';
```

### Phase 4: API Updates
1. Update models (Pydantic schemas)
2. Update repository functions
3. Update API endpoints
4. Update MCP tools

### Phase 5: Deprecation
1. Keep old stock_balances table read-only for compatibility
2. All writes go to stock_balances_v2
3. Eventually rename tables

---

## MCP Tool Updates

### New Tools
```python
# Godown management
@mcp.tool()
async def create_godown(code: str, name: str, address: str = None) -> dict:
    """Create a new godown/warehouse"""

@mcp.tool()
async def list_godowns() -> list[dict]:
    """List all active godowns"""

@mcp.tool()
async def set_default_godown(godown_id: int) -> dict:
    """Set a godown as the default"""

# Tone management
@mcp.tool()
async def create_tone(variant_id: int, suffix: str, description: str = None) -> dict:
    """Create a new tone for a variant"""

@mcp.tool()
async def list_tones(variant_id: int) -> list[dict]:
    """List all tones for a variant"""

# Transfer
@mcp.tool()
async def transfer_stock(
    variant_id: int,
    tone_id: int,
    qty: float,
    uom: Literal["m", "roll"],
    from_godown_id: int,
    to_godown_id: int,
    reason: str = None
) -> dict:
    """Transfer stock between godowns"""
```

### Updated Tools
```python
# Stock receipt - add tone/godown support
@mcp.tool()
async def receive_stock(
    variant_id: int,
    qty: float,
    uom: Literal["m", "roll"],
    roll_count: int = None,
    document_id: str = None,
    reason: str = None,
    # New parameters
    tone_id: int = None,
    tone_suffix: str = None,  # Creates new tone if doesn't exist
    godown_id: int = None     # Uses default if not specified
) -> dict:
    """Receive stock into inventory with tone and godown tracking"""

# Stock issue - require tone
@mcp.tool()
async def issue_stock(
    variant_id: int,
    qty: float,
    uom: Literal["m", "roll"],
    tone_id: int,             # REQUIRED
    godown_id: int = None,
    reason: str = None,
    document_id: str = None
) -> dict:
    """Issue stock from inventory (must specify tone to prevent mixing)"""
```

---

## Backward Compatibility

### Approach: Graceful Degradation
1. **tone_id = NULL in movements** → Treated as legacy data
2. **godown_id = NULL** → Uses default godown
3. **Old API calls without tone/godown** → Work with defaults
4. **New API calls** → Full tone/godown tracking

### Example: Old-style receive still works
```python
# Old call (no tone/godown)
POST /receive {"variant_id": 991, "qty": 100, "uom": "m"}

# System behavior:
# 1. Creates new tone with auto-suffix (or uses "UNSPEC")
# 2. Uses default godown
# 3. Records movement with tone_id and godown_id populated
```

---

## Implementation Order

### Step 1: Database Changes
- [ ] Add godowns table and schema
- [ ] Add tones table and schema
- [ ] Add columns to stock_movements
- [ ] Create stock_balances_v2 table
- [ ] Write migration scripts

### Step 2: Repository Layer
- [ ] Add godown CRUD functions
- [ ] Add tone CRUD functions
- [ ] Update movement creation to use new fields
- [ ] Update balance queries for composite key
- [ ] Add transfer function

### Step 3: API Models
- [ ] Create Godown Pydantic models
- [ ] Create Tone Pydantic models
- [ ] Update StockBalance models
- [ ] Update MovementCreate models

### Step 4: API Endpoints
- [ ] Add /godowns routes
- [ ] Add /tones routes
- [ ] Update /receive, /issue, /adjust
- [ ] Add /transfer route
- [ ] Update /stock queries

### Step 5: MCP Tools
- [ ] Add godown tools
- [ ] Add tone tools
- [ ] Update stock movement tools
- [ ] Add transfer tool

### Step 6: Migration
- [ ] Create default godown
- [ ] Migrate existing balances
- [ ] Update existing movements (optional backfill)

---

## Edge Cases & Validation

### 1. Tone Validation
- Cannot issue from a tone with insufficient stock
- Cannot issue mixing tones (exactly one tone_id per issue)
- Tone suffix must be unique per variant

### 2. Godown Validation
- Cannot delete godown with stock (use RESTRICT)
- Exactly one default godown must exist
- Cannot transfer to same godown

### 3. Stock Negative Prevention (Optional)
```sql
-- Add check constraint
ALTER TABLE stock_balances_v2
ADD CONSTRAINT chk_non_negative CHECK (on_hand_m >= 0);
```

---

## Questions for Clarification

1. **Tone Suffix Format**: Should suffixes be single letters (A, B, C), numbers (01, 02), or flexible?

2. **Auto-tone on Receipt**: When receiving new stock, should the system:
   - Require explicit tone specification?
   - Auto-create new tone with next letter?
   - Prompt user for tone choice?

3. **Godown Requirement**: Should godown_id be:
   - Optional (uses default)?
   - Required on all operations?
   - Required only when multiple godowns exist?

4. **Legacy Data**: How should pre-migration stock be treated:
   - Create "LEGACY" tone for each?
   - Create "UNSPECIFIED" tone?
   - Require manual assignment?

5. **Transfer Tracking**: Should transfers between godowns be:
   - Single TRANSFER movement type?
   - Pair of ISSUE + RECEIPT movements?
   - Separate transfer log table?

---

## Summary

This plan introduces:
1. **Tones** - Sub-division of variants for batch/dye lot tracking
2. **Godowns** - Warehouse location tracking with default support
3. **Enhanced Stock Model** - Stock tracked at `(variant, tone, godown)` level
4. **Business Rule Enforcement** - Issues require single tone to prevent mixing
5. **Backward Compatibility** - Existing API calls continue to work

The design maintains the current system's simplicity while adding the necessary granularity for real-world textile inventory management.
