from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.core.database_pool import db_pool

CENT = Decimal("0.01")


class PropertyNotFoundError(Exception):
    """Raised when a property does not exist for the requesting tenant."""


def to_money(value: Any) -> Decimal:
    """Round a stored amount (NUMERIC(10,3)) to cents once, after aggregation."""
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _month_bounds(month: int, year: int) -> tuple[datetime, datetime]:
    """Naive start/end of a calendar month, compared against property-local time."""
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Revenue for one property of one tenant, optionally limited to a calendar month.

    A month is evaluated in the property's own timezone, so a booking that checks in at
    23:30 UTC on 29 Feb at a Paris property counts toward March, as the client expects.
    Errors propagate to the caller: we never return placeholder figures.
    """
    params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}
    period_filter = ""
    if month is not None and year is not None:
        params["start"], params["end"] = _month_bounds(month, year)
        period_filter = """
            AND (r.check_in_date AT TIME ZONE p.timezone) >= :start
            AND (r.check_in_date AT TIME ZONE p.timezone) <  :end
        """

    query = text(f"""
        SELECT
            p.id                              AS property_id,
            COALESCE(SUM(r.total_amount), 0)  AS total_revenue,
            COUNT(r.id)                       AS reservation_count,
            COUNT(DISTINCT r.currency)        AS currency_count,
            MIN(r.currency)                   AS currency
        FROM properties p
        LEFT JOIN reservations r
               ON r.property_id = p.id
              AND r.tenant_id  = p.tenant_id
              {period_filter}
        WHERE p.id = :property_id
          AND p.tenant_id = :tenant_id
        GROUP BY p.id
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        row = (await session.execute(query, params)).fetchone()

    if row is None:
        raise PropertyNotFoundError(property_id)
    if row.currency_count > 1:
        # Summing different currencies would silently produce a wrong number.
        raise ValueError(f"Mixed currencies for property {property_id}; conversion required")

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(to_money(row.total_revenue)),
        "currency": row.currency or "USD",
        "count": row.reservation_count,
        "month": month,
        "year": year,
    }


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Properties that belong to the tenant, for the dashboard selector."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY name"),
            {"tenant_id": tenant_id},
        )
        return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in result.fetchall()]