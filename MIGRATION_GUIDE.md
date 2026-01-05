# Migration Guide: Business Identifier Update

This guide covers breaking changes for applications integrating with the Traider API (REST or MCP).

## Overview

The system now uses **business identifiers** (`fabric_code` + `color_code`) instead of internal IDs (`variant_id`) for all variant and stock operations. This aligns with how businesses naturally identify inventory.

---

## Breaking Changes Summary

| Area | Before | After |
|------|--------|-------|
| Variant identification | `variant_id` (integer) | `fabric_code` + `color_code` (strings) |
| Variant uniqueness | `(fabric_id, color_code, gsm, width, finish)` | `(fabric_id, color_code)` |
| Stock movements | Required `variant_id` | Requires `fabric_code` + `color_code` |
| Stock queries | `GET /stock?variant_id=123` | `GET /stock/{fabric_code}/{color_code}` |

---

## REST API Changes

### 1. Stock Movements (BREAKING)

**Before:**
```json
POST /receive
{
  "variant_id": 123,
  "qty": 100,
  "uom": "m"
}
```

**After:**
```json
POST /receive
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001",
  "qty": 100,
  "uom": "m"
}
```

Same change applies to:
- `POST /issue`
- `POST /adjust`

### 2. Stock Queries

**Before:**
```
GET /stock?variant_id=123&uom=m
```

**After (Primary):**
```
GET /stock/{fabric_code}/{color_code}?uom=m
GET /stock/CTN-001/BLK-9001?uom=m
```

**Fallback (still works):**
```
GET /stock?variant_id=123&uom=m
```

### 3. Variant CRUD - New Nested Routes

**Before:**
```
POST /variants
{
  "fabric_id": 1,
  "color_code": "BLK-9001",
  "finish": "Bio"
}

GET /variants/123
PUT /variants/123
DELETE /variants/123
```

**After (Primary - Nested):**
```
POST /fabrics/{fabric_code}/variants
{
  "color_code": "BLK-9001",
  "finish": "Bio"
}

GET /fabrics/{fabric_code}/variants/{color_code}
PUT /fabrics/{fabric_code}/variants/{color_code}
DELETE /fabrics/{fabric_code}/variants/{color_code}
```

**Fallback (still works for reads):**
```
GET /variants?fabric_code=CTN-001&color_code=BLK-9001
GET /variants/123  (by internal ID)
```

### 4. Variant Creation - No More `fabric_id`

**Before:**
```json
POST /variants
{
  "fabric_id": 1,
  "color_code": "BLK-9001",
  "finish": "Bio"
}
```

**After:**
```json
POST /fabrics/CTN-001/variants
{
  "color_code": "BLK-9001",
  "finish": "Bio"
}
```

Note: `fabric_id` is no longer in the request body - it comes from the URL path.

### 5. Fabric Responses - Now Include Aliases

**Before:**
```json
{
  "id": 1,
  "fabric_code": "CTN-001",
  "name": "Cotton Jersey",
  "image_url": null
}
```

**After:**
```json
{
  "id": 1,
  "fabric_code": "CTN-001",
  "name": "Cotton Jersey",
  "image_url": null,
  "aliases": ["Single Jersey", "T-shirt Fabric"]
}
```

### 6. New Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /fabrics/{fabric_code}` | Get fabric by code (not ID) |
| `GET /fabrics/{fabric_code}/aliases` | List fabric aliases |
| `POST /fabrics/{fabric_code}/aliases` | Add alias `{"alias": "..."}` |
| `DELETE /fabrics/{fabric_code}/aliases/{alias}` | Remove alias |
| `GET /search?q=...` | Unified search across fabrics + variants |

---

## MCP Tool Changes

### 1. Variant Operations (BREAKING)

**Before:**
```json
// create_variant
{
  "fabric_id": 1,
  "color_code": "BLK-9001",
  "finish": "Bio"
}

// get_variant
{
  "variant_id": 123
}

// update_variant
{
  "variant_id": 123,
  "color_code": "BLK-9002"
}
```

**After:**
```json
// create_variant
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001",
  "finish": "Bio"
}

// get_variant
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001"
}

// update_variant
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001",
  "new_color_code": "BLK-9002"  // optional, for renaming
}
```

### 2. Stock Operations (BREAKING)

**Before:**
```json
// receive_stock, issue_stock, adjust_stock
{
  "variant_id": 123,
  "qty": 100,
  "uom": "m"
}

// get_stock
{
  "variant_id": 123,
  "uom": "m"
}
```

**After:**
```json
// receive_stock, issue_stock, adjust_stock
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001",
  "qty": 100,
  "uom": "m"
}

// get_stock
{
  "fabric_code": "CTN-001",
  "color_code": "BLK-9001",
  "uom": "m"
}
```

### 3. Fabric Operations

**Before:**
```json
// update_fabric
{
  "fabric_id": 1,
  "name": "New Name"
}
```

**After:**
```json
// update_fabric
{
  "fabric_code": "CTN-001",
  "name": "New Name"
}
```

### 4. New MCP Tools

| Tool | Description |
|------|-------------|
| `add_alias` | Add alias to fabric `{fabric_code, alias}` |
| `remove_alias` | Remove alias from fabric `{fabric_code, alias}` |
| `unified_search` | Search fabrics + variants `{q, include_fabrics, include_variants}` |

### 5. Removed MCP Tools

| Tool | Replacement |
|------|-------------|
| `get_stock_batch` | Use `search_variants` with `include_stock: true` |

---

## Migration Steps

### For REST API Clients

1. **Update stock movement calls** to use `fabric_code` + `color_code` instead of `variant_id`

2. **Update stock query calls** to use the new path-based endpoint:
   ```
   /stock/{fabric_code}/{color_code}
   ```

3. **If creating variants**, switch to nested routes:
   ```
   POST /fabrics/{fabric_code}/variants
   ```

4. **Handle new `aliases` field** in fabric responses (array of strings)

5. **Consider using unified search** for cross-entity queries

### For MCP Clients

1. **Update all tool calls** that used `variant_id` or `fabric_id`:
   - `create_variant`: Replace `fabric_id` with `fabric_code`
   - `update_variant`: Replace `variant_id` with `fabric_code` + `color_code`
   - `get_variant`: Replace `variant_id` with `fabric_code` + `color_code`
   - `receive_stock`: Replace `variant_id` with `fabric_code` + `color_code`
   - `issue_stock`: Replace `variant_id` with `fabric_code` + `color_code`
   - `adjust_stock`: Replace `variant_id` with `fabric_code` + `color_code`
   - `get_stock`: Replace `variant_id` with `fabric_code` + `color_code`
   - `update_fabric`: Replace `fabric_id` with `fabric_code`

2. **Use new tools** for alias management and unified search

---

## Schema Changes

### Variant Uniqueness

**Before:** Same `color_code` could exist multiple times per fabric with different GSM/width/finish:
```
Fabric: CTN-001
  - BLK-9001, gsm=180, width=60, finish=Bio
  - BLK-9001, gsm=200, width=60, finish=Bio  ← Different GSM, same color
```

**After:** `color_code` must be unique per fabric:
```
Fabric: CTN-001
  - BLK-9001, gsm=180, width=60, finish=Bio
  - BLK-9001-200, gsm=200, width=60, finish=Bio  ← Must use different color_code
```

If you need multiple specs for the same color, encode specs in the color_code (e.g., `BLK-9001-180GSM`).

---

## Quick Reference

### Old → New Parameter Mapping

| Old Parameter | New Parameter(s) |
|---------------|------------------|
| `variant_id` | `fabric_code` + `color_code` |
| `fabric_id` | `fabric_code` |

### Endpoint Quick Reference

| Operation | Old | New |
|-----------|-----|-----|
| Get variant | `GET /variants/123` | `GET /fabrics/CTN-001/variants/BLK-9001` |
| Create variant | `POST /variants` | `POST /fabrics/CTN-001/variants` |
| Update variant | `PUT /variants/123` | `PUT /fabrics/CTN-001/variants/BLK-9001` |
| Delete variant | `DELETE /variants/123` | `DELETE /fabrics/CTN-001/variants/BLK-9001` |
| Get stock | `GET /stock?variant_id=123` | `GET /stock/CTN-001/BLK-9001` |
| Receive stock | `POST /receive {variant_id}` | `POST /receive {fabric_code, color_code}` |
| Issue stock | `POST /issue {variant_id}` | `POST /issue {fabric_code, color_code}` |
| Adjust stock | `POST /adjust {variant_id}` | `POST /adjust {fabric_code, color_code}` |
