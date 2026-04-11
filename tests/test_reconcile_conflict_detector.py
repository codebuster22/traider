"""Tests for reconcile.conflict_detector — cross-reference TargetGroups with DB state."""
from decimal import Decimal
import pytest

from traider import repo
from traider.reconcile.models import TargetGroup
from traider.reconcile.conflict_detector import detect_conflicts


@pytest.fixture
def lycra(clean_db):
    repo.create_fabric(fabric_code="LYC", name="Lycra")


def _group(primary="910", aliases=None, fabric_code="LYC"):
    return TargetGroup(
        fabric_code=fabric_code, fabric_name="Lycra", finish="Standard",
        gsm=None, width=None,
        primary_color_code=primary, alias_codes=aliases or [],
        total_mtr=Decimal("100"), source_rows=[2],
    )


class TestConflictDetector:
    def test_no_conflicts_when_everything_new(self, lycra):
        groups = [_group(primary="910", aliases=["1101"])]
        conflicts = detect_conflicts(groups)
        assert conflicts == []

    def test_no_conflict_when_single_variant_exists_matching(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        groups = [_group(primary="910", aliases=["1101"])]
        assert detect_conflicts(groups) == []

    def test_cross_group_alias_conflict(self, lycra):
        # 1101 is currently an alias of variant 888; 888 is NOT in the sheet's group
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="888", finish="Standard")
        v = repo.get_variant_by_codes("LYC", "888")
        repo.add_variant_alias_direct(v["fabric_id"], v["id"], "1101")
        groups = [_group(primary="910", aliases=["1101"])]
        conflicts = detect_conflicts(groups)
        assert len(conflicts) == 1
        assert conflicts[0].code == "CROSS_GROUP_ALIAS_CONFLICT"
        assert conflicts[0].existing_variant_primary == "888"

    def test_multiple_existing_variants_need_merge_when_both_have_stock(self, lycra):
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="1101", finish="Standard")
        repo.create_movement_by_codes("LYC", "910", "RECEIPT", 100.0, "m")
        repo.create_movement_by_codes("LYC", "1101", "RECEIPT", 50.0, "m")
        groups = [_group(primary="910", aliases=["1101"])]
        conflicts = detect_conflicts(groups)
        assert len(conflicts) == 1
        assert conflicts[0].code == "MULTIPLE_EXISTING_VARIANTS_NEED_MERGE"

    def test_multiple_existing_no_stock_is_NOT_a_conflict(self, lycra):
        """Silent merge path — handled by Branch 0 of writer, not flagged as conflict."""
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="910", finish="Standard")
        repo.create_variant_by_fabric_code(fabric_code="LYC", color_code="1101", finish="Standard")
        groups = [_group(primary="910", aliases=["1101"])]
        assert detect_conflicts(groups) == []
