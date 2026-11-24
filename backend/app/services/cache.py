import json
import logging
import os
from typing import Any, Dict, Optional

import redis.asyncio as redis

from app.services.reservations import calculate_total_revenue

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

REVENUE_CACHE_TTL_SECONDS = 300


def revenue_cache_key(tenant_id: str, property_id: str, month: Optional[int], year: Optional[int]) -> str:
    # Property IDs are only unique per tenant (composite PK), so the tenant MUST be part of the key.
    period = f"{year}-{month:02d}" if month and year else "all"
    return f"revenue:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """Revenue summary with a tenant-scoped read-through cache."""
    cache_key = revenue_cache_key(tenant_id, property_id, month, year)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            # Defence in depth: never serve an entry that belongs to another tenant.
            if data.get("tenant_id") == tenant_id:
                return data
            logger.error("Tenant mismatch in revenue cache for key %s", cache_key)
    except redis.RedisError as exc:
        logger.warning("Revenue cache read failed, falling back to DB: %s", exc)

    result = await calculate_total_revenue(property_id, tenant_id, month, year)

    try:
        await redis_client.setex(cache_key, REVENUE_CACHE_TTL_SECONDS, json.dumps(result))
    except redis.RedisError as exc:
        logger.warning("Revenue cache write failed: %s", exc)

    return result