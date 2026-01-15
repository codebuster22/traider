# Implementation Plan: Code Sanitization & Confirmation Flow

## Problem Statement

Users make slight mistakes in color codes when entering via text (e.g., "905(A)" vs "905 (A)"), causing the agent to create duplicate variants instead of recognizing existing ones. This happens because there's no sanitization/normalization layer - codes pass directly to the backend.

---

## Feature 1: Code Sanitization (Implement Now)

### Design Approach

**Key Principle**: Offload sanitization from LLM to deterministic code.

#### Sanitization Rules

| Code Type | Allowed Characters | Transformation |
|-----------|-------------------|----------------|
| `color_code` | `A-Z`, `0-9` | Uppercase, remove whitespace, remove special chars |
| `fabric_code` | `A-Z`, `0-9`, `_` | Uppercase, spaces → underscore, remove special chars |

#### Examples
```
# Color codes
"905(A)"    → "905A"
"905 (A)"   → "905A"
"B-920"     → "B920"
"  123  "   → "123"

# Fabric codes
"Mull Dobby"    → "MULL_DOBBY"
"Cotton-Jersey" → "COTTON_JERSEY"
"Lycra 4-way"   → "LYCRA_4WAY"
```

---

### Implementation Steps

#### Step 1: Create `src/traider_agent/utils/code_utils.py`

New file with sanitization functions:
- `sanitize_color_code(raw: str) -> str` - Alphanumeric only, uppercase
- `sanitize_fabric_code(raw: str) -> str` - Alphanumeric + underscore, uppercase
- `is_valid_color_code(code: str) -> bool` - Validation check
- `is_valid_fabric_code(code: str) -> bool` - Validation check
- `is_significant_change(original: str, sanitized: str) -> bool` - Returns True if change is more than just whitespace/case

**Significant change detection:**
```python
def is_significant_change(original: str, sanitized: str) -> bool:
    """Check if sanitization made a significant change (not just whitespace/case).

    Returns True if characters were removed/transformed beyond:
    - Whitespace removal
    - Case change

    Examples:
        "905A" vs "905A" → False (no change)
        "905 a" vs "905A" → False (just whitespace + case)
        "905(A)" vs "905A" → True (parentheses removed)
        "B-920" vs "B920" → True (dash removed)
    """
    # Normalize both to uppercase, remove whitespace, compare
    normalized_original = re.sub(r'\s', '', original.upper())
    return normalized_original != sanitized
```

#### Step 2: Modify `src/traider_agent/tools/backend_tools.py`

Add sanitization at the start of each function that accepts `fabric_code` or `color_code`.

**Key behavior**: When significant sanitization occurs (not just whitespace/case), include it in the response so agent can inform user:

```python
async def create_variant(...) -> dict:
    original_color = color_code
    color_code = sanitize_color_code(color_code)
    fabric_code = sanitize_fabric_code(fabric_code)

    result = await rest_post(...)

    # Add sanitization info if significant change
    if is_significant_change(original_color, color_code):
        result["_sanitized"] = {
            "original_color_code": original_color,
            "sanitized_color_code": color_code,
        }
    return result
```

Agent can then say: "I've standardized '905(A)' to '905A' for consistency."

**Functions to modify (16 total):**
- `create_fabric` - sanitize `fabric_code`
- `update_fabric` - sanitize `fabric_code`
- `search_fabrics` - sanitize `fabric_code` param (if provided)
- `create_variant` - sanitize both codes
- `update_variant` - sanitize all code params
- `get_variant` - sanitize both codes
- `search_variants` - sanitize both params (if provided)
- `create_variants_batch` - sanitize `fabric_code` AND each variant's `color_code`
- `search_variants_batch` - sanitize all codes
- `get_stock` - sanitize both codes
- `receive_stock` - sanitize both codes
- `issue_stock` - sanitize both codes
- `adjust_stock` - sanitize both codes
- `receive_stock_batch` - sanitize each item's codes
- `issue_stock_batch` - sanitize each item's codes

#### Step 3: Backend Migration Logic Specs (for backend team to implement)

**Migration Name**: `sanitize_codes_cleanup_v1`

---

##### Part A: Sanitize Fabric Codes

**Sanitization Rules for `fabric_code`:**
```
Input: "Mull Dobby", "Cotton-Jersey", "Lycra 4-way!"
Output: "MULL_DOBBY", "COTTON_JERSEY", "LYCRA_4WAY"

Steps:
1. Convert to UPPERCASE
2. Replace whitespace and dashes with underscore (_)
3. Remove all characters except A-Z, 0-9, _
4. Collapse multiple underscores (__ → _)
5. Trim leading/trailing underscores
```

**Logic:**
```
FOR each fabric in fabrics table:
    sanitized_code = sanitize_fabric_code(fabric.fabric_code)

    IF sanitized_code == fabric.fabric_code:
        SKIP (no change needed)

    IF sanitized_code already exists in fabrics table:
        LOG conflict: "Cannot rename {fabric_code} to {sanitized_code} - already exists"
        SKIP (manual resolution needed)

    ELSE:
        UPDATE fabric SET fabric_code = sanitized_code WHERE id = fabric.id
        UPDATE all variants WHERE fabric_code = old_code SET fabric_code = sanitized_code
        UPDATE all stock_movements WHERE fabric_code = old_code SET fabric_code = sanitized_code
        LOG: "Renamed fabric {old_code} → {sanitized_code}"
```

---

##### Part B: Sanitize Color Codes

**Sanitization Rules for `color_code`:**
```
Input: "905(A)", "905 (A)", "B-920", "  123  "
Output: "905A", "905A", "B920", "123"

Steps:
1. Convert to UPPERCASE
2. Remove ALL characters except A-Z, 0-9
```

**Logic:**
```
FOR each variant in variants table:
    sanitized_code = sanitize_color_code(variant.color_code)

    IF sanitized_code == variant.color_code:
        SKIP (no change needed)

    # Check conflict within same fabric
    IF sanitized_code already exists for variant.fabric_code:
        LOG conflict: "Cannot rename {fabric_code}/{color_code} to {sanitized_code} - already exists"
        SKIP (manual resolution needed - may need to merge)

    ELSE:
        UPDATE variant SET color_code = sanitized_code WHERE id = variant.id
        UPDATE all stock_movements WHERE fabric_code = variant.fabric_code AND color_code = old_code
               SET color_code = sanitized_code
        LOG: "Renamed {fabric_code}/{old_code} → {fabric_code}/{sanitized_code}"
```

---

##### Part C: Delete Corrupted Stock Movements

**Context**: On 2026-01-15, session context pollution caused the agent to hallucinate and execute incorrect stock operations for gunjanfabrics firm.

**Logic:**
```
DELETE FROM stock_movements
WHERE firm_id = (SELECT id FROM firms WHERE firm_name ILIKE '%gunjan%')
  AND created_at >= '2026-01-15T00:00:00Z'

LOG: "Deleted {count} corrupted stock movements for gunjanfabrics since 2026-01-15"
```

**Warning**: This will delete ALL stock movements for gunjanfabrics since Jan 15, 2026. Make sure this is intended before running.

---

##### Part D: Update Stock Balances (After Deletion)

After deleting corrupted movements, recalculate stock balances:

```
FOR each variant affected by deleted movements:
    new_balance = SUM(qty) FROM stock_movements WHERE variant_id = variant.id
    UPDATE stock_balances SET on_hand = new_balance WHERE variant_id = variant.id
```

Or if using a trigger-based system, the deletion may auto-recalculate.

---

##### Migration Tracking

Track migration completion to ensure it runs only once:

```sql
CREATE TABLE IF NOT EXISTS migrations (
    name VARCHAR(255) PRIMARY KEY,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Check before running:
SELECT 1 FROM migrations WHERE name = 'sanitize_codes_cleanup_v1';

-- Mark complete after:
INSERT INTO migrations (name) VALUES ('sanitize_codes_cleanup_v1');
```

#### Step 4: Add Unit Tests `tests/test_code_utils.py`

Test cases for sanitization functions covering edge cases.

#### Step 5: Update Agent Instructions (Optional)

Add to `fabric_manager.py` or `root_agent.py` instructions:

```
## Code Standardization Notifications
When tool responses include `_sanitized` field, inform the user:
"I've standardized '{original}' to '{sanitized}' for consistency."
```

This is optional since the agent may naturally notice and report this from the response.

---

## Feature 2: Button-based Confirmation (Design Only - NOT implementing)

### Current State
Agent uses text-based confirmations via `pending_context` system. User wants button-based confirmation to offload from LLM.

### Proposed Flow (for future implementation)
1. Agent calls `queue_action(action_type, action_data, summary)` tool
2. System sends WhatsApp interactive message with [Yes] [No] buttons
3. User clicks button
4. Webhook callback executes or rejects the queued action

### Requirements (for future)
- WhatsApp interactive message support
- `action_queue` table or extend `pending_contexts`
- Webhook handler for button callbacks
- Modified agent flow to wait for button response

---

## Files to Modify

### Agent Project (this repo)

| File | Action | Changes |
|------|--------|---------|
| `src/traider_agent/utils/code_utils.py` | CREATE | Sanitization functions |
| `src/traider_agent/utils/__init__.py` | MODIFY | Export new functions |
| `src/traider_agent/tools/backend_tools.py` | MODIFY | Add sanitization to 16 functions |
| `tests/test_code_utils.py` | CREATE | Unit tests |

### Backend Project (separate repo - specs provided above)

Migration logic specs are provided in Step 3 above. Backend team to implement based on their architecture.

---

## Verification Steps

1. **Unit tests pass**
   ```bash
   pytest tests/test_code_utils.py -v
   ```

2. **Manual test sanitization**
   - Create variant with "905 (A)" → should become "905A"
   - Search for "905A" → should find it
   - Try creating "905(A)" → should NOT create duplicate (finds existing)

3. **Migration dry-run**
   ```bash
   python -m scripts.migrate_codes --dry-run
   ```

4. **End-to-end agent test**
   - Send: "Add variant 905 (A) to LYCRA"
   - Verify backend receives "905A"

---

## Edge Cases

1. **Migration conflicts**: If "905A" and "905(A)" both exist as variants, migration detects conflict and logs for manual resolution (no auto-merge)

2. **Empty input**: All functions handle empty strings gracefully, returning empty string

3. **Already valid codes**: Codes that are already valid pass through unchanged
