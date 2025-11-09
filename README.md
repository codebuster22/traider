# v1 Traider - An AI powered OS for Textile Trades

# Problem statement (business-first)

Teams need a **single, dead-simple source of truth** to answer:

> **“How much stock do we have for this specific fabric variant right now?”**

Today this is error-prone and scattered. We want a tiny service that:

* Stores **fabrics** and **variants** (with images and color codes).
* Records **stock movements** (receive/issue/adjust) in **meters** while accepting **rolls** as input.
* Returns **on-hand balance** fast, in meters and rolls.
* Lets users **search** fabrics/variants quickly.

No authentication. Keep everything minimal and predictable.

---

# Business logic & rules

* **Entity flow:** Create **Fabric** → Create **Variant** → Post **Movements** → Read **Stock**.
* **UOM handling:** API accepts `"m"` or `"roll"`; DB **only stores meters**.
  Constant: `ROLL_TO_M = 200`.
  `delta_qty_m = qty` if `uom=="m"` else `qty * 200`.
* **On-hand math:** For each `variant_id`, `on_hand_m` is the cumulative sum of `delta_qty_m`.
  Derived on read:

  * `on_hand_rolls = on_hand_m / 200`
  * `whole_rolls = floor(on_hand_m / 200)`
  * `remainder_m = on_hand_m - whole_rolls*200`
* **Movement types:** `RECEIPT`, `ISSUE`, `ADJUST` (each carries a free-text `reason`).
* **Simplicity defaults (MVP):**

  * Negative stock **allowed**.
  * No auth/RBAC.
  * No lots/locations/reservations/valuation.
  * IDs used everywhere (pass `variant_id`).

---

# Scope (what needs to be done)

**In (MVP)**

1. CRUD-lite for **Fabrics** and **Variants** (create-only for MVP; read/search).
2. **Movements**: `/receive`, `/issue`, `/adjust` (IDs only, UOM=m/roll, with `reason`).
3. **Stock read** for a variant (meters + rolls).
4. **Search** endpoints:

   * `/fabrics` (free text & exact filters)
   * `/variants` (free text, attribute filters, optional stock join)

**Out (deferred)**

* Lots/rolls as physical units, locations, reservations, valuation, idempotency, invoices/PO links, events, auth.

---

# Tech specs

## Stack & runtime

* **Language/Framework:** Python 3.11+, **FastAPI**
* **DB:** **Postgres** (connect via `DATABASE_URL`)
* **Driver:** `psycopg` v3
* **Startup:** Always run DDL (`CREATE TABLE IF NOT EXISTS …`) so tables/indexes exist.

## Environment

* `DATABASE_URL=postgresql://user:pass@host:5432/inventory`

## Project layout (suggested)

```
app/
  main.py            # FastAPI app, startup init_db()
  db.py              # connect(), init_db(), helpers
  models.py          # Pydantic schemas
  repo.py            # SQL helpers (lookup, insert, upsert)
  routes/
    fabrics.py
    variants.py
    movements.py
    stock.py
```

---

## API (final)

### 1) Master data

#### POST `/fabrics`

Create a fabric.

```json
{
  "fabric_code": "FAB-001",
  "name": "Cotton Jersey",
  "image_url": "https://…/fabrics/cotton-jersey.jpg"
}
```

**201**

```json
{ "id": 1, "fabric_code": "FAB-001", "name": "Cotton Jersey", "image_url": "https://…/fabrics/cotton-jersey.jpg" }
```

#### POST `/variants`

Create a variant under a fabric.

```json
{
  "fabric_id": 1,
  "color_code": "BLK-9001",
  "gsm": 180,
  "width": 72,
  "finish": "Bio",
  "image_url": "https://…/variants/1-BLK-9001.jpg"
}
```

**201**

```json
{
  "id": 10, "fabric_id": 1, "color_code": "BLK-9001",
  "gsm": 180, "width": 72, "finish": "Bio",
  "image_url": "https://…/variants/1-BLK-9001.jpg"
}
```

#### GET `/variants/{variant_id}`

Returns the variant plus joined fabric basics.
**200**

```json
{
  "id": 10,
  "fabric_id": 1,
  "fabric_code": "FAB-001",
  "fabric_name": "Cotton Jersey",
  "fabric_image_url": "https://…/fabrics/cotton-jersey.jpg",
  "color_code": "BLK-9001",
  "gsm": 180,
  "width": 72,
  "finish": "Bio",
  "variant_image_url": "https://…/variants/1-BLK-9001.jpg"
}
```

---

### 2) Movements (IDs only; DB stores meters)

Common request body:

```json
{ "variant_id": 10, "qty": 3.0, "uom": "roll", "reason": "PO-2219 initial receipt" }
```

Common success:

```json
{
  "movement_id": 42,
  "movement_type": "RECEIPT",
  "delta_qty_m": 600.0,
  "on_hand_m_after": 1240.5
}
```

#### POST `/receive`

* Sets `movement_type = "RECEIPT"`

#### POST `/issue`

* Sets `movement_type = "ISSUE"`

#### POST `/adjust`

* Sets `movement_type = "ADJUST"`

Validation:

* 404 if `variant_id` unknown.
* 400 if `uom` not in `{"m","roll"}` or `qty` invalid.

---

### 3) Stock read

#### GET `/stock?variant_id=10&uom=roll`

**200**

```json
{
  "variant_id": 10,
  "fabric_id": 1,
  "fabric_code": "FAB-001",
  "fabric_name": "Cotton Jersey",
  "fabric_image_url": "https://…/fabrics/cotton-jersey.jpg",
  "color_code": "BLK-9001",
  "gsm": 180,
  "width": 72,
  "finish": "Bio",
  "variant_image_url": "https://…/variants/1-BLK-9001.jpg",

  "on_hand_m": 350.0,
  "on_hand_rolls": 1.75,
  "whole_rolls": 1,
  "remainder_m": 150.0,

  "uom": "roll",
  "updated_at": "2025-11-09T09:12:03Z"
}
```

*(Optional)* **GET `/stock/batch?variant_ids=10,11,12&uom=roll`** → array of the same shape.

---

### 4) Search

#### GET `/fabrics`

Search fabrics by free text or fields.
Query params:

* `q` (partial across `fabric_code`, `name`)
* `fabric_code`, `name` (exact/partial)
* `limit` (default 20, max 100), `offset` (default 0)
* `sort_by` ∈ `id|fabric_code|name` (default `fabric_code`)
* `sort_dir` ∈ `asc|desc` (default `asc`)

**200**

```json
{
  "items": [
    {"id":1,"fabric_code":"FAB-001","name":"Cotton Jersey","image_url":"https://…/fabrics/cotton.jpg"}
  ],
  "limit":20,"offset":0,"total":1
}
```

#### GET `/variants`

Search variants; can include stock.
Query params (all optional unless noted):

* **Free text:** `q` (partial over `color_code`, `finish`, `fabric_code`, `fabric_name`)
* **Filters:** `fabric_id`, `fabric_code`, `color_code` (partial ok), `gsm`, `gsm_min`, `gsm_max`, `width`, `width_min`, `width_max`, `finish` (partial ok)
* **Stock:** `include_stock` (bool), `in_stock_only` (bool; implies include_stock)
* **Paging/sort:** `limit` (20/100), `offset` (0), `sort_by` ∈ `id|fabric_code|color_code|gsm|width|finish|on_hand_m`, `sort_dir` ∈ `asc|desc`

**200 (include_stock=true)**

```json
{
  "items": [
    {
      "id":10,"fabric_id":1,"fabric_code":"FAB-001","fabric_name":"Cotton Jersey",
      "fabric_image_url":"https://…/fabrics/cotton.jpg",
      "color_code":"BLK-9001","gsm":180,"width":72,"finish":"Bio",
      "variant_image_url":"https://…/variants/1-BLK-9001.jpg",
      "on_hand_m":350.0,"on_hand_rolls":1.75,"whole_rolls":1,"remainder_m":150.0,
      "updated_at":"2025-11-09T09:12:03Z"
    }
  ],
  "limit":20,"offset":0,"total":1
}
```

---

## Database schema (Postgres DDL)

> Run at startup (idempotent). Also create helpful indexes and trigram extension.

```sql
-- Fuzzy search helpers
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS fabrics (
  id BIGSERIAL PRIMARY KEY,
  fabric_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS fabric_variants (
  id BIGSERIAL PRIMARY KEY,
  fabric_id BIGINT NOT NULL REFERENCES fabrics(id) ON DELETE CASCADE,
  color_code TEXT NOT NULL,
  gsm INT NOT NULL,
  width INT NOT NULL,
  finish TEXT NOT NULL,
  image_url TEXT,
  UNIQUE (fabric_id, color_code, gsm, width, finish)
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
  reason TEXT,                          -- free-text remark
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
CREATE INDEX IF NOT EXISTS idx_variants_fabric_keys
  ON fabric_variants (fabric_id, color_code, gsm, width, finish);
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
```

---

## Core DB operations (app-level transactions)

**Insert movement & upsert balance (single transaction):**

1. Validate `variant_id` exists.
2. Compute `delta_qty_m` from `qty,uom` with `ROLL_TO_M=200`.
3. `INSERT` into `stock_movements` and `RETURNING id`.
4. Upsert balance:

```sql
INSERT INTO stock_balances (variant_id, on_hand_m, updated_at)
VALUES ($1, $2, now())
ON CONFLICT (variant_id) DO UPDATE
SET on_hand_m = stock_balances.on_hand_m + EXCLUDED.on_hand_m,
    updated_at = now();
```

5. `SELECT on_hand_m` to return `on_hand_m_after`.

**Search queries:** build dynamic SQL with optional filters; when `include_stock=true`, `LEFT JOIN stock_balances`.

---

## Startup behavior (FastAPI)

* On app `startup`:

  * Connect via `DATABASE_URL`.
  * Execute the full DDL block above.
  * Keep a small connection pool (or open per-request for simplicity).

---

## Validation & errors

* **400** — invalid `uom` (must be `m` or `roll`), missing/invalid `qty`, bad pagination params.
* **404** — `variant_id` or `fabric_id` not found (for respective endpoints).
* **200/201** — success; always return the canonical/derived numbers in meters and rolls where applicable.

---

## Acceptance criteria (MVP)

1. **Create master data**

   * `POST /fabrics` → `id`.
   * `POST /variants` → `id`.
   * `GET /stock?variant_id={id}` returns `on_hand_m = 0`.

2. **Receive in rolls**

   * `POST /receive {variant_id, qty:3, uom:"roll"}` increases `on_hand_m` by **600**.

3. **Issue in meters**

   * `POST /issue {variant_id, qty:150, uom:"m"}` decreases `on_hand_m` by **150**.

4. **Adjust with reason**

   * `POST /adjust {variant_id, qty:-0.5, uom:"roll", reason:"recount"}` decreases by **100** and stores `reason`.

5. **Read stock (roll view)**

   * `GET /stock?variant_id={id}&uom=roll` returns correct `on_hand_rolls`, `whole_rolls`, `remainder_m`.

6. **Search**

   * `/fabrics?q=cot` matches fabric name/code.
   * `/variants?q=blk&include_stock=true` includes stock fields and filters correctly.
   * `/variants?in_stock_only=true` returns only variants with `on_hand_m > 0`.
