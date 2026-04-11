"""Reconcile writer — stage 10 of the pipeline (see spec §6.4.3).

Runs inside a single SERIALIZABLE transaction. On any failure, the entire
reconcile is rolled back — zero writes.
"""
from decimal import Decimal
from typing import Optional

from traider import repo
from traider.db import sanitize_fabric_code
from traider.reconcile.models import (
    ReconcileAction, ReconcileSummary, TargetGroup,
)


def execute_reconcile(
    groups: list[TargetGroup],
    batch_id: str,
    reason: str,
) -> tuple[ReconcileSummary, list[ReconcileAction]]:
    """Execute stage 10 of the pipeline. Assumes stages 1-9 already passed.

    Returns (summary, actions).
    """
    summary = ReconcileSummary()
    actions: list[ReconcileAction] = []
    document_id = f"reconcile:{batch_id}"
    fabrics_touched: set[str] = set()

    with repo.get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")

                for group in groups:
                    fabrics_touched.add(group.fabric_code)

                    # Ensure fabric exists
                    cur.execute(
                        "SELECT id FROM fabrics WHERE fabric_code = %s",
                        (group.fabric_code,),
                    )
                    fabric_row = cur.fetchone()
                    if fabric_row is None:
                        cur.execute(
                            "INSERT INTO fabrics (fabric_code, name) VALUES (%s, %s) RETURNING id",
                            (group.fabric_code, group.fabric_name),
                        )
                        fabric_id = cur.fetchone()["id"]
                        summary.fabrics_created += 1
                        actions.append(ReconcileAction(
                            type="fabric_created",
                            fabric_code=group.fabric_code,
                            payload={"fabric_name": group.fabric_name},
                        ))
                    else:
                        fabric_id = fabric_row["id"]

                    # Branch 0: silent merge of stock-free duplicates.
                    # Compute distinct resolved variants from the group's codes.
                    # We call _execute_link_on_cursor (NOT _execute_link) so the merge
                    # happens inside our already-open SERIALIZABLE transaction — this
                    # preserves atomicity with the subsequent Branch 1/2/3 writes.
                    all_codes = [group.primary_color_code, *group.alias_codes]
                    resolved_vids = set()
                    for c in all_codes:
                        vid = repo._resolve_variant_id_on_cursor(cur, group.fabric_code, c)
                        if vid is not None:
                            resolved_vids.add(vid)

                    if len(resolved_vids) > 1:
                        # Branch 0 — safe because conflict detector (stage 9) guaranteed
                        # no merge sources have stock. confirm=True because we've already
                        # validated safety at stage 9.
                        link_result = repo._execute_link_on_cursor(
                            cur, fabric_id, group.fabric_code, all_codes, confirm=True,
                        )
                        if link_result["result"] == "linked":
                            summary.aliases_created += len(link_result.get("aliases_added", []))

                    # Re-resolve using the cursor-aware helper so Branch 0's
                    # uncommitted merges are visible to this lookup
                    survivor_vid = repo._resolve_variant_id_on_cursor(
                        cur, group.fabric_code, group.primary_color_code
                    )

                    if survivor_vid is None:
                        # Check if any alias in the group resolves to an existing variant.
                        # This handles the case where the sheet's primary (e.g. 910) is new
                        # but one of its aliases (e.g. 1101) was previously a standalone primary.
                        # In that case we promote the sheet's primary by renaming the existing
                        # variant's color_code and registering the old primary as an alias.
                        for code in group.alias_codes:
                            alt_vid = repo._resolve_variant_id_on_cursor(cur, group.fabric_code, code)
                            if alt_vid is not None:
                                # Rename this variant's primary to the sheet's primary_color_code
                                cur.execute(
                                    "UPDATE fabric_variants SET color_code = %s WHERE id = %s",
                                    (group.primary_color_code, alt_vid),
                                )
                                # Register the old primary as an alias so it still resolves
                                repo._add_variant_alias_on_cursor(cur, fabric_id, alt_vid, code)
                                summary.aliases_created += 1
                                survivor_vid = alt_vid
                                break

                    if survivor_vid is None:
                        # Branch 1 — variant doesn't exist, create it
                        cur.execute(
                            """
                            INSERT INTO fabric_variants (fabric_id, color_code, finish, gsm, width)
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING id
                            """,
                            (
                                fabric_id, group.primary_color_code, group.finish,
                                group.gsm, group.width,
                            ),
                        )
                        survivor_vid = cur.fetchone()["id"]
                        summary.variants_created += 1

                        # Add each alias using the cursor-aware helper (stays in txn)
                        for alias in group.alias_codes:
                            added = repo._add_variant_alias_on_cursor(
                                cur, fabric_id, survivor_vid, alias
                            )
                            if added:
                                summary.aliases_created += 1

                        # Post opening ADJUST movement
                        _post_reconcile_adjust(
                            cur, survivor_vid, group.total_mtr,
                            reason=reason, document_id=document_id,
                        )
                        summary.movements_posted += 1
                        summary.total_delta_m += group.total_mtr
                        actions.append(ReconcileAction(
                            type="variant_created",
                            fabric_code=group.fabric_code,
                            payload={
                                "color_code": group.primary_color_code,
                                "aliases": group.alias_codes,
                                "opening_m": float(group.total_mtr),
                            },
                        ))
                    else:
                        # Branch 2 or 3 — variant exists, possibly add new aliases then adjust.
                        # Branch 3 bits: add any aliases from sheet not yet on the variant.
                        new_aliases_added: list[str] = []
                        for alias in group.alias_codes:
                            existing_vid = repo._resolve_variant_id_on_cursor(
                                cur, group.fabric_code, alias
                            )
                            if existing_vid != survivor_vid:
                                added = repo._add_variant_alias_on_cursor(
                                    cur, fabric_id, survivor_vid, alias
                                )
                                if added:
                                    new_aliases_added.append(alias)
                                    summary.aliases_created += 1

                        # Compute delta against current balance
                        cur.execute(
                            "SELECT COALESCE(on_hand_m, 0) AS on_hand_m FROM stock_balances WHERE variant_id = %s FOR UPDATE",
                            (survivor_vid,),
                        )
                        bal_row = cur.fetchone()
                        current_m = Decimal(str(bal_row["on_hand_m"])) if bal_row else Decimal(0)
                        delta = group.total_mtr - current_m

                        if delta == 0:
                            summary.variants_already_balanced += 1
                            actions.append(ReconcileAction(
                                type="variant_already_balanced",
                                fabric_code=group.fabric_code,
                                payload={
                                    "color_code": group.primary_color_code,
                                    "balance_m": float(current_m),
                                },
                            ))
                        else:
                            _post_reconcile_adjust(
                                cur, survivor_vid, delta,
                                reason=reason, document_id=document_id,
                            )
                            summary.variants_adjusted += 1
                            summary.movements_posted += 1
                            summary.total_delta_m += delta
                            action_payload = {
                                "color_code": group.primary_color_code,
                                "previous_m": float(current_m),
                                "target_m": float(group.total_mtr),
                                "delta_m": float(delta),
                            }
                            if new_aliases_added:
                                action_payload["aliases_added"] = new_aliases_added
                            actions.append(ReconcileAction(
                                type="variant_adjusted",
                                fabric_code=group.fabric_code,
                                payload=action_payload,
                            ))

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    summary.fabrics_touched = len(fabrics_touched)
    return summary, actions


def _post_reconcile_adjust(cur, variant_id: int, delta_m: Decimal, reason: str, document_id: str):
    """Insert an ADJUST movement and upsert the balance. Mirrors repo.create_movement pattern."""
    cur.execute(
        """
        INSERT INTO stock_movements (
            variant_id, movement_type, delta_qty_m, original_qty, original_uom,
            reason, document_id
        ) VALUES (%s, 'ADJUST', %s, %s, 'm', %s, %s)
        """,
        (variant_id, delta_m, delta_m, reason, document_id),
    )
    cur.execute(
        """
        INSERT INTO stock_balances (variant_id, on_hand_m, on_hand_rolls, updated_at)
        VALUES (%s, %s, 0, now())
        ON CONFLICT (variant_id) DO UPDATE
        SET on_hand_m = stock_balances.on_hand_m + EXCLUDED.on_hand_m,
            updated_at = now()
        """,
        (variant_id, delta_m),
    )
