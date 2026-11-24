import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Convert a standard Postgres URL to the asyncpg dialect SQLAlchemy expects."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgres://", "postgresql+asyncpg://", 1
    )


class DatabasePool:
    """Process-wide async connection pool, initialised once and reused."""

    def __init__(self) -> None:
        self.engine = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self.session_factory is not None:
            return
        async with self._lock:
            if self.session_factory is not None:
                return
            # Async engines use AsyncAdaptedQueuePool by default; the sync QueuePool is not allowed here.
            self.engine = create_async_engine(
                _async_database_url(settings.database_url),
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
                pool_recycle=settings.database_pool_recycle,
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine, class_=AsyncSession, expire_on_commit=False
            )
            logger.info("Database connection pool initialized")

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Return a session usable as `async with db_pool.get_session() as session:`."""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()


# Global database pool instance
db_pool = DatabasePool()


async def get_db_session():
    """FastAPI dependency yielding a database session."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session