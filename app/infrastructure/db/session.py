"""Async database engine creation."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.config import DatabaseSettings


def normalize_database_url(url: str) -> str:
    """Normalize Render/local PostgreSQL URLs for psycopg 3 async usage."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
