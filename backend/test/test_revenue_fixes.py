from datetime import datetime
from decimal import Decimal

from app.services.cache import revenue_cache_key
from app.services.reservations import _month_bounds, to_money


def test_cache_key_is_tenant_scoped():
    # Both tenants own a property called prop-001; their cache entries must never collide.
    assert revenue_cache_key("tenant-a", "prop-001", None, None) != revenue_cache_key("tenant-b", "prop-001", None, None)


def test_cache_key_is_period_scoped():
    assert revenue_cache_key("tenant-a", "prop-001", 3, 2024) == "revenue:tenant-a:prop-001:2024-03"
    assert revenue_cache_key("tenant-a", "prop-001", 3, 2024) != revenue_cache_key("tenant-a", "prop-001", 4, 2024)


def test_money_rounds_once_after_summing():
    # Three sub-cent amounts sum exactly to 1000.000 and display as 1000.00, not 999.99.
    total = sum([Decimal("333.333"), Decimal("333.333"), Decimal("333.334")])
    assert to_money(total) == Decimal("1000.00")
    assert to_money(Decimal("0.005")) == Decimal("0.01")  # half-up, not banker's rounding


def test_month_bounds_handle_december():
    assert _month_bounds(12, 2024) == (datetime(2024, 12, 1), datetime(2025, 1, 1))