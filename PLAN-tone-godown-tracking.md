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

#### 3. `stock_balances` - New Composite Key (Breaking Change)
```sql
-- Drop old table and recreate with new schema
DROP TABLE IF EXISTS stock_balances;

CREATE TABLE stock_balances (
    variant_id   BIGINT NOT NULL REFERENCES fabric_variants(id) ON DELETE CASCADE,
    tone_id      BIGINT NOT NULL REFERENCES tones(id) ON DELETE CASCADE,
    godown_id    BIGINT NOT NULL REFERENCES godowns(id) ON DELETE RESTRICT,
    on_hand_m    NUMERIC(14,3) DEFAULT 0,
    on_hand_rolls NUMERIC(14,3) DEFAULT 0,
    updated_at   TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (variant_id, tone_id, godown_id)
);

CREATE INDEX idx_stock_balances_variant ON stock_balances(variant_id);
CREATE INDEX idx_stock_balances_godown ON stock_balances(godown_id);
CREATE INDEX idx_stock_balances_tone ON stock_balances(tone_id);

-- Prevent negative stock
ALTER TABLE stock_balances
ADD CONSTRAINT chk_non_negative CHECK (on_hand_m >= 0);
```

#### 4. `stock_movements` - Add Required Tracking Fields (Breaking Change)
```sql
-- Recreate table with required tone/godown columns
DROP TABLE IF EXISTS stock_movements;

CREATE TABLE stock_movements (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ DEFAULT now(),
    variant_id      BIGINT NOT NULL REFERENCES fabric_variants(id) ON DELETE CASCADE,
    tone_id         BIGINT NOT NULL REFERENCES tones(id) ON DELETE CASCADE,
    godown_id       BIGINT NOT NULL REFERENCES godowns(id) ON DELETE RESTRICT,
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('RECEIPT','ISSUE','ADJUST','TRANSFER')),
    delta_qty_m     NUMERIC(14,3) NOT NULL,
    original_qty    NUMERIC(14,3) NOT NULL,
    original_uom    TEXT NOT NULL CHECK (original_uom IN ('m','roll')),
    roll_count      INT,
    document_id     TEXT,
    reason          TEXT,
    -- For TRANSFER movements: destination godown
    transfer_to_godown_id BIGINT REFERENCES godowns(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_movements_variant ON stock_movements(variant_id);
CREATE INDEX idx_movements_tone ON stock_movements(tone_id);
CREATE INDEX idx_movements_godown ON stock_movements(godown_id);
CREATE INDEX idx_movements_type ON stock_movements(movement_type);
CREATE INDEX idx_movements_ts ON stock_movements(ts);
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
# New schema (Breaking Change - tone_id and godown_id now required)
class MovementCreate(BaseModel):
    variant_id: int
    tone_id: int              # REQUIRED - which tone
    godown_id: int            # REQUIRED - which godown
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int] = None
    document_id: Optional[str] = None
    reason: Optional[str] = None

# Alternative for /receive - can create tone inline
class ReceiveCreate(BaseModel):
    variant_id: int
    godown_id: int            # REQUIRED
    qty: float
    uom: Literal["m", "roll"]
    roll_count: Optional[int] = None
    document_id: Optional[str] = None
    reason: Optional[str] = None
    # Tone: provide ONE of these
    tone_id: Optional[int] = None         # Use existing tone
    new_tone_suffix: Optional[str] = None # Create new tone with this suffix
```

#### Receive Stock - Tone Handling
```python
# Scenario 1: Add to existing tone
POST /receive
{
    "variant_id": 991,
    "tone_id": 1,       # Existing tone A
    "godown_id": 1,     # REQUIRED
    "qty": 500,
    "uom": "m"
}

# Scenario 2: Create new tone on receive
POST /receive
{
    "variant_id": 991,
    "new_tone_suffix": "B",  # Creates tone B
    "godown_id": 1,
    "qty": 200,
    "uom": "m",
    "reason": "New batch, slightly darker"
}
```

#### Issue Stock - All Fields Required
```python
# Both tone_id and godown_id are required
POST /issue
{
    "variant_id": 991,
    "tone_id": 1,       # REQUIRED - from which tone
    "godown_id": 1,     # REQUIRED - from which godown
    "qty": 400,
    "uom": "m",
    "document_id": "INV-2024-001"
}
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

## Migration Strategy (Breaking Change - Clean Slate)

Since breaking changes are allowed, we do a clean migration:

### Step 1: Create New Tables
```sql
-- Run in order due to FK dependencies
1. CREATE godowns table
2. INSERT default godown
3. CREATE tones table
4. DROP and CREATE stock_movements (new schema)
5. DROP and CREATE stock_balances (new schema)
```

### Step 2: Seed Default Godown
```sql
INSERT INTO godowns (code, name, is_default)
VALUES ('MAIN', 'Main Godown', TRUE);
```

### Step 3: Historical Data
- Existing stock_movements and stock_balances are **dropped**
- Start fresh with new schema
- If data preservation needed, export before migration

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
# Stock receipt - tone and godown required
@mcp.tool()
async def receive_stock(
    variant_id: int,
    godown_id: int,           # REQUIRED
    qty: float,
    uom: Literal["m", "roll"],
    tone_id: int = None,      # Use existing tone OR
    new_tone_suffix: str = None,  # Create new tone
    roll_count: int = None,
    document_id: str = None,
    reason: str = None
) -> dict:
    """Receive stock into inventory with tone and godown tracking.
    Must provide either tone_id (existing) or new_tone_suffix (creates new)."""

# Stock issue - all required
@mcp.tool()
async def issue_stock(
    variant_id: int,
    tone_id: int,             # REQUIRED
    godown_id: int,           # REQUIRED
    qty: float,
    uom: Literal["m", "roll"],
    reason: str = None,
    document_id: str = None
) -> dict:
    """Issue stock from inventory. Both tone_id and godown_id required."""

# Stock adjust - all required
@mcp.tool()
async def adjust_stock(
    variant_id: int,
    tone_id: int,             # REQUIRED
    godown_id: int,           # REQUIRED
    qty: float,               # Can be positive or negative
    uom: Literal["m", "roll"],
    reason: str               # REQUIRED for adjustments
) -> dict:
    """Adjust stock (corrections). Both tone_id and godown_id required."""
```

---

## Implementation Order

### Step 1: Database Changes
- [ ] Add godowns table and schema
- [ ] Add tones table and schema
- [ ] Recreate stock_movements with new schema
- [ ] Recreate stock_balances with composite key
- [ ] Seed default godown

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

### Step 6: Testing
- [ ] Test godown CRUD operations
- [ ] Test tone CRUD operations
- [ ] Test receive with new/existing tone
- [ ] Test issue requires tone_id and godown_id
- [ ] Test transfer between godowns
- [ ] Test negative stock prevention

---

## Edge Cases & Validation

### 1. Tone Validation
- Cannot issue from a tone with insufficient stock
- Tone suffix must be unique per variant
- Must provide either `tone_id` or `new_tone_suffix` on receive

### 2. Godown Validation
- Cannot delete godown with stock (FK RESTRICT)
- Exactly one default godown must exist
- Cannot transfer to same godown

### 3. Stock Validation
- Negative stock prevented by CHECK constraint
- Issue fails if balance insufficient

---

## Questions for Clarification

1. **Tone Suffix Format**: Should suffixes be single letters (A, B, C), numbers (01, 02), or flexible (user decides)?

2. **Transfer Tracking**: Should transfers between godowns be:
   - Single TRANSFER movement type with `transfer_to_godown_id`?
   - Pair of ISSUE + RECEIPT movements linked by `document_id`?

---

## Summary

This plan introduces:
1. **Tones** - Sub-division of variants for batch/dye lot tracking
2. **Godowns** - Warehouse location tracking with default support
3. **Enhanced Stock Model** - Stock tracked at `(variant, tone, godown)` level
4. **Business Rule Enforcement** - All movements require `tone_id` and `godown_id`
5. **Negative Stock Prevention** - CHECK constraint prevents overselling

**Breaking Changes:**
- `stock_balances` table recreated with composite PK `(variant_id, tone_id, godown_id)`
- `stock_movements` table recreated with required `tone_id` and `godown_id`
- All movement APIs require `tone_id` and `godown_id` parameters
- Historical data not preserved (clean slate migration)
