"""
Async SQLAlchemy engine and session factory.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
else:
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for request-scoped dependency injection."""

    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create tables for development when migrations are not applied."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
