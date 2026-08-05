import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.config.settings import DatabaseSettings
from app.infrastructure.db.session import create_engine, create_session_factory

pytestmark = pytest.mark.database


@pytest_asyncio.fixture(scope="session")
async def database_engine() -> AsyncIterator[AsyncEngine]:
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("set RUN_DATABASE_TESTS=1 with a migrated PostgreSQL database")
    url = os.environ["DATABASE_URL"]
    engine = create_engine(DatabaseSettings(app_env="test", database_url=url))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def database_sessions(
    database_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    tables = (
        "audit_logs, telegram_updates, callback_challenges, workspace_strategies, "
        "notification_destinations, workspace_memberships, workspaces, access_requests, "
        "platform_users"
    )
    async with database_engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield create_session_factory(database_engine)
