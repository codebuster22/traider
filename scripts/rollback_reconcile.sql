-- Rollback a reconciliation batch. Run in psql as:
--   psql $DATABASE_URL -v batch_id='reconcile_20260411_153022_ab12' -f rollback_reconcile.sql
--
-- This soft-cancels every movement from the batch and recomputes balances for the
-- affected variants. Fabrics, variants, and aliases created by the batch are NOT
-- deleted — only the movements are undone. If you need to delete variants too, you
-- must do that by hand after running this script.

BEGIN;

-- 1. Soft-cancel all movements from the batch
UPDATE stock_movements
   SET is_cancelled = true,
       cancelled_at = now()
 WHERE document_id = 'reconcile:' || :'batch_id'
   AND is_cancelled = false;

-- 2. Find affected variants
CREATE TEMP TABLE affected_variants AS
SELECT DISTINCT variant_id
  FROM stock_movements
 WHERE document_id = 'reconcile:' || :'batch_id';

-- 3. Recompute balances for affected variants from remaining non-cancelled movements
UPDATE stock_balances sb
   SET on_hand_m = COALESCE((
         SELECT SUM(delta_qty_m)
           FROM stock_movements
          WHERE variant_id = sb.variant_id
            AND is_cancelled = false
       ), 0),
       on_hand_rolls = COALESCE((
         SELECT SUM(COALESCE(roll_count, 0))
           FROM stock_movements
          WHERE variant_id = sb.variant_id
            AND is_cancelled = false
       ), 0),
       updated_at = now()
 WHERE variant_id IN (SELECT variant_id FROM affected_variants);

-- 4. Report what was undone
SELECT 'movements_cancelled' AS metric,
       COUNT(*) AS value
  FROM stock_movements
 WHERE document_id = 'reconcile:' || :'batch_id'
   AND is_cancelled = true;

-- Inspect `affected_variants` before committing if you want to verify
-- COMMIT; or ROLLBACK; based on verification
