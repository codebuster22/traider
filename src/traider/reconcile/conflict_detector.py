"""Reconcile conflict detector — stage 9 of the pipeline (see spec §6.4.2)."""
from traider import repo
from traider.reconcile.models import ReconcileConflict, TargetGroup


def detect_conflicts(groups: list[TargetGroup]) -> list[ReconcileConflict]:
    """Cross-reference each target group with current DB state.

    Returns a list of conflicts. If non-empty, the pipeline returns 409 and
    writes nothing.
    """
    conflicts: list[ReconcileConflict] = []

    for group in groups:
        all_codes = [group.primary_color_code, *group.alias_codes]
        expected_group_set = set(all_codes)

        # Resolve each code; gather distinct variants they belong to
        resolved_by_code: dict[str, int] = {}
        for code in all_codes:
            vid = repo.resolve_variant_id(group.fabric_code, code)
            if vid is not None:
                resolved_by_code[code] = vid
        distinct_vids = list(set(resolved_by_code.values()))

        if not distinct_vids:
            continue  # all new — no conflict
        if len(distinct_vids) == 1:
            # Single variant — check CROSS_GROUP_ALIAS_CONFLICT by verifying its
            # primary is in the sheet's group
            vid = distinct_vids[0]
            with repo.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT color_code FROM fabric_variants WHERE id = %s", (vid,))
                    row = cur.fetchone()
                    existing_primary = row["color_code"] if row else None

            if existing_primary and existing_primary not in expected_group_set:
                conflicting_code = next(c for c, v in resolved_by_code.items() if v == vid)
                conflicts.append(ReconcileConflict(
                    code="CROSS_GROUP_ALIAS_CONFLICT",
                    row=group.source_rows[0],
                    fabric_code=group.fabric_code,
                    color_code=conflicting_code,
                    existing_variant_primary=existing_primary,
                    remediation=f"/link {group.primary_color_code} {conflicting_code}",
                    message=(
                        f"COLOUR NO. '{conflicting_code}' currently belongs to variant "
                        f"'{existing_primary}' which is not in this alias group. Either run "
                        f"/link {group.primary_color_code} {conflicting_code} via WhatsApp to "
                        f"move it first, or add '{existing_primary}' to the alias group in your "
                        f"sheet and re-upload."
                    ),
                ))
            continue

        # Multiple variants resolve — check if any has stock
        any_has_stock = False
        stocked_codes: list[str] = []
        for vid in distinct_vids:
            with repo.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT v.color_code,
                               COALESCE(sb.on_hand_m, 0) AS on_hand_m,
                               (SELECT COUNT(*) FROM stock_movements sm
                                 WHERE sm.variant_id = v.id AND sm.is_cancelled = false) AS mc
                          FROM fabric_variants v
                          LEFT JOIN stock_balances sb ON sb.variant_id = v.id
                         WHERE v.id = %s
                        """,
                        (vid,),
                    )
                    row = cur.fetchone()
                    if row and (float(row["on_hand_m"] or 0) > 0 or row["mc"] > 0):
                        any_has_stock = True
                        stocked_codes.append(row["color_code"])

        if any_has_stock:
            stocked_list = " ".join(stocked_codes)
            conflicts.append(ReconcileConflict(
                code="MULTIPLE_EXISTING_VARIANTS_NEED_MERGE",
                row=group.source_rows[0],
                fabric_code=group.fabric_code,
                color_code=group.primary_color_code,
                existing_variant_primary=None,
                remediation=f"/link {group.primary_color_code} {' '.join(c for c in stocked_codes if c != group.primary_color_code)}",
                message=(
                    f"Variants {stocked_list} all exist with stock history and must be merged "
                    f"before reconciling. Run /link {group.primary_color_code} "
                    f"{' '.join(c for c in stocked_codes if c != group.primary_color_code)} "
                    f"via WhatsApp first, then re-upload the sheet."
                ),
            ))
        # else: multiple variants with no stock → Branch 0 of writer will silently merge

    return conflicts
