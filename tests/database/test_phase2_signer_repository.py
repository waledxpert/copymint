import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.ids import uuid7
from app.infrastructure.db.session import normalize_database_url
from app.signer.service import SignerWalletService
from app.signer.storage import SqlAlchemySignerEnvelopeRepository
from tests.unit.test_signer_envelope import FakeDataKeyProvider

pytestmark = pytest.mark.database


@pytest.mark.asyncio
async def test_signer_repository_is_idempotent_and_restorable(
    signer_database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    service = SignerWalletService(
        SqlAlchemySignerEnvelopeRepository(signer_database_sessions),
        FakeDataKeyProvider(),
        environment="test",
    )
    workspace_id = uuid7()
    first = await service.create_wallet(
        workspace_id=workspace_id, chain_id=1, idempotency_key="wallet-request-001"
    )
    repeated = await service.create_wallet(
        workspace_id=workspace_id, chain_id=1, idempotency_key="wallet-request-001"
    )
    assert first.created
    assert not repeated.created
    assert repeated.signer_key_id == first.signer_key_id
    assert (
        await service.verify_restore(
            signer_key_id=first.signer_key_id, workspace_id=workspace_id, chain_id=1
        )
        == first.address
    )


@pytest.mark.asyncio
async def test_application_database_role_cannot_connect_to_signer_database() -> None:
    if os.getenv("RUN_DATABASE_TESTS") != "1":
        pytest.skip("set RUN_DATABASE_TESTS=1 with isolated test databases")
    application_url = make_url(normalize_database_url(os.environ["DATABASE_URL"]))
    signer_url = make_url(normalize_database_url(os.environ["SIGNER_DATABASE_URL"]))
    isolated_url = signer_url.set(
        username=application_url.username,
        password=application_url.password,
    )
    engine = create_async_engine(isolated_url)
    try:
        with pytest.raises(DBAPIError):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1 FROM signer_key_envelopes"))
    finally:
        await engine.dispose()
