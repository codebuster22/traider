# Batch API Implementation Status Report

**Date:** 2026-01-05
**Status:** Complete

---

## Overview

Batch REST API endpoints have been added to reduce HTTP overhead for bulk operations. All endpoints are also exposed via MCP for agent discovery.

All endpoints use **business identifiers** (`fabric_code` + `color_code`) per the existing migration guide.

---

## Implemented Endpoints

| # | Endpoint | Method | Description |
|---|----------|--------|-------------|
| 1 | `/fabrics/{fabric_code}/variants/batch` | POST | Create multiple variants under a fabric |
| 2 | `/receive/batch` | POST | Receive stock for multiple variants |
| 3 | `/issue/batch` | POST | Issue stock for multiple variants |
| 4 | `/fabrics/{fabric_code}/variants/search/batch` | POST | Search multiple variants by color codes |

---

## MCP Tools Added

| Tool Name | REST Equivalent |
|-----------|-----------------|
| `create_variants_batch` | `POST /fabrics/{fabric_code}/variants/batch` |
| `receive_stock_batch` | `POST /receive/batch` |
| `issue_stock_batch` | `POST /issue/batch` |
| `search_variants_batch` | `POST /fabrics/{fabric_code}/variants/search/batch` |

---

## Request/Response Formats

### 1. Create Variants Batch

**Request:**
```json
POST /fabrics/{fabric_code}/variants/batch
{
  "variants": [
    {"color_code": "2", "finish": "plain", "gsm": null, "width": null},
    {"color_code": "3", "finish": "plain"}
  ]
}
```

**Response:**
```json
{
  "created": [
    {"fabric_code": "LYCRA", "color_code": "2", "finish": "plain"}
  ],
  "failed": [
    {"color_code": "3", "error": "Variant with color_code '3' already exists"}
  ],
  "summary": {"total": 2, "created": 1, "failed": 1}
}
```

### 2. Receive Stock Batch

**Request:**
```json
POST /receive/batch
{
  "items": [
    {"fabric_code": "LYCRA", "color_code": "2", "qty": 500, "uom": "m", "roll_count": 5},
    {"fabric_code": "LYCRA", "color_code": "3", "qty": 300, "uom": "m", "roll_count": 3}
  ],
  "document_id": "MILL-2024-001",
  "reason": "Mill receipt from ABC Mills"
}
```

**Response:**
```json
{
  "processed": [
    {"fabric_code": "LYCRA", "color_code": "2", "qty": 500, "previous_balance": 1000, "new_balance": 1500, "movement_id": 101}
  ],
  "failed": [
    {"fabric_code": "LYCRA", "color_code": "3", "qty": 300, "error": "Variant '3' not found for fabric 'LYCRA'"}
  ],
  "summary": {"total": 2, "processed": 1, "failed": 1, "total_qty": 500}
}
```

### 3. Issue Stock Batch

**Request:**
```json
POST /issue/batch
{
  "items": [
    {"fabric_code": "LYCRA", "color_code": "919", "qty": 236.20, "uom": "m", "roll_count": 2}
  ],
  "customer_name": "M/s. ADESHWAR FASHION",
  "document_id": "INV-857"
}
```

**Response:** Same structure as receive batch.

### 4. Search Variants Batch

**Request:**
```json
POST /fabrics/{fabric_code}/variants/search/batch
{
  "color_codes": ["919", "917", "A920B"],
  "include_stock": true
}
```

**Response:**
```json
{
  "found": [
    {
      "color_code": "919",
      "variant": {"id": 1, "fabric_code": "LYCRA", "color_code": "919", "finish": "plain", ...},
      "stock": {"balance": 1500, "uom": "m"}
    }
  ],
  "not_found": ["A920B"],
  "summary": {"total": 3, "found": 2, "not_found": 1}
}
```

---

## Deviations from Initial Spec

### 1. UOM Values

| Aspect | Spec | Implementation | Reason |
|--------|------|----------------|--------|
| Allowed values | `m \| pcs \| kg` | `m \| roll` | **Consistency** - The existing codebase uses `m \| roll` throughout. Using different UOM values for batch endpoints would create confusion and require conversion logic. |

### 2. Field Naming: `rolls` vs `roll_count`

| Aspect | Spec | Implementation | Reason |
|--------|------|----------------|--------|
| Roll quantity field | `rolls` | `roll_count` | **Consistency** - The existing `MovementCreate` model uses `roll_count`. Maintaining consistent naming across single and batch operations simplifies client code. |

### 3. Insufficient Stock Handling (Issue Batch)

| Aspect | Spec | Implementation | Reason |
|--------|------|----------------|--------|
| Stock validation | Fail if insufficient, optional `allow_negative: true` | **No validation, negative allowed by default** | **User requirement** - Per clarification, negative stock is allowed by default. This simplifies the API and matches business needs where stock reconciliation may happen after the fact. |

### 4. Transaction Handling

| Aspect | Spec | Implementation | Reason |
|--------|------|----------------|--------|
| Atomicity | Not specified | **Independent per-item** | **User requirement** - Per clarification, each item is processed independently. Partial success returns 207 Multi-Status. This prevents a single bad item from blocking the entire batch. |

### 5. Response Field: `rolls` in processed items

| Aspect | Spec | Implementation | Reason |
|--------|------|----------------|--------|
| Response includes | `rolls` field shown | Not included | The `roll_count` is already tracked in the movement record. The response focuses on meter balances since meters are the source of truth. Clients can query full stock details separately if needed. |

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 201 | All items processed successfully |
| 207 | Partial success (some succeeded, some failed) |
| 400 | Invalid request body / validation error / batch size exceeded |
| 404 | Resource not found (fabric_code for nested routes) |

---

## Batch Size Limits

| Endpoint | Max Batch Size |
|----------|---------------|
| Create variants batch | 100 |
| Receive stock batch | 50 |
| Issue stock batch | 50 |
| Search variants batch | No limit |

---

## Files Modified

| File | Changes |
|------|---------|
| `src/traider/models.py` | Added 12 Pydantic models for batch operations |
| `src/traider/repo.py` | Added `create_variants_batch`, `create_movements_batch`, `search_variants_batch` |
| `src/traider/routes/variants.py` | Added batch create and search endpoints |
| `src/traider/routes/movements.py` | Added receive/issue batch endpoints |
| `src/traider/mcp.py` | Added 4 MCP tools with input schemas |

---

## Integration Notes for Downstream Services

1. **Authentication:** None (single-tenant internal design)

2. **Content-Type:** All requests use `application/json`

3. **Error Handling:**
   - Check HTTP status code first (201 = full success, 207 = partial)
   - Always check `failed` array in response for item-level errors
   - `summary` object provides quick counts

4. **Idempotency:**
   - Variant creation: Duplicate `color_code` will fail with error message
   - Stock movements: Not idempotent - each call creates new movement records

5. **Rate Limits:** None currently configured

---

## Testing Checklist

- [ ] Create variants batch - all succeed
- [ ] Create variants batch - partial success (duplicate color_code)
- [ ] Create variants batch - fabric not found (404)
- [ ] Receive batch - all succeed
- [ ] Receive batch - variant not found (partial success)
- [ ] Issue batch - all succeed
- [ ] Issue batch - negative balance allowed
- [ ] Search batch - all found
- [ ] Search batch - partial found
- [ ] MCP tools - verify all 4 tools are discoverable
