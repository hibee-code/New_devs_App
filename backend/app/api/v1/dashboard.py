import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFoundError, list_tenant_properties

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_tenant(current_user) -> str:
    """Fail closed: a request with no resolved tenant must never see data."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant associated with user")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user=Depends(get_current_user)) -> List[Dict[str, Any]]:
    tenant_id = _require_tenant(current_user)
    return await list_tenant_properties(tenant_id)


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="month and year must be provided together")

    tenant_id = _require_tenant(current_user)

    try:
        revenue = await get_revenue_summary(property_id, tenant_id, month, year)
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except Exception:
        logger.exception("Revenue calculation failed for %s/%s", tenant_id, property_id)
        # Better an honest error than a made-up number on a financial dashboard.
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")

    return {
        "property_id": revenue["property_id"],
        # Decimal string (e.g. "2250.00"): no float rounding drift on money.
        "total_revenue": revenue["total"],
        "currency": revenue["currency"],
        "reservations_count": revenue["count"],
        "month": revenue["month"],
        "year": revenue["year"],
    }