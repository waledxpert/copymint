from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.access.context import TelegramIdentity
from app.application.access.service import AccessService
from app.application.wallets.ports import SignerWalletResult
from app.application.wallets.service import WalletLimitReached, WalletService
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import ExecutionWallet
from app.infrastructure.db.repositories.access import (
    SqlAlchemyAccessRepository,
    set_workspace_context,
)
from app.infrastructure.db.repositories.wallets import SqlAlchemyWalletRepository

pytestmark = pytest.mark.database
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def identity(user_id: int) -> TelegramIdentity:
    return TelegramIdentity(user_id, user_id, "private", username=f"user{user_id}")


class FakeSigner:
    async def create_wallet(self, **values: object) -> SignerWalletResult:
        workspace_id = values["workspace_id"]
        chain_id = values["chain_id"]
        assert hasattr(workspace_id, "int") and isinstance(chain_id, int)
        address = f"0x{workspace_id.int % (16**40):040x}"  # type: ignore[union-attr]
        return SignerWalletResult(
            signer_key_id=uuid7(),
            workspace_id=workspace_id,  # type: ignore[arg-type]
            chain_id=chain_id,
            address=address,
            created=True,
        )


@pytest.mark.asyncio
async def test_wallets_are_private_idempotent_and_limited(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    access = AccessService(
        SqlAlchemyAccessRepository(database_sessions),
        platform_owner_ids=frozenset({1}),
        clock=lambda: NOW,
    )
    owner = await access.resolve_context(identity(1))
    contexts = []
    for user_id in (99, 100):
        request = await access.request_access(identity(user_id))
        assert request.request_id is not None
        await access.approve(owner, request.request_id)
        contexts.append(await access.resolve_context(identity(user_id)))

    wallet_repository = SqlAlchemyWalletRepository(database_sessions)
    service = WalletService(
        wallet_repository,
        FakeSigner(),  # type: ignore[arg-type]
        max_wallets_per_workspace=1,
    )
    first, created = await service.create_wallet(contexts[0], idempotency_key="wallet-user-99-01")
    repeated, repeated_created = await service.create_wallet(
        contexts[0], idempotency_key="wallet-user-99-01"
    )
    second, _ = await service.create_wallet(contexts[1], idempotency_key="wallet-user-100-1")
    assert created and not repeated_created and repeated.id == first.id
    assert await service.list_wallets(contexts[0]) == [first]
    assert await service.list_wallets(contexts[1]) == [second]
    with pytest.raises(WalletLimitReached):
        await service.create_wallet(contexts[0], idempotency_key="wallet-user-99-02")

    assert contexts[0].workspace_id is not None
    assert await wallet_repository.update_balance(
        workspace_id=contexts[0].workspace_id,
        wallet_id=first.id,
        balance_wei=10**18,
        block_number=20_000_000,
        refreshed_at=NOW,
    )
    refreshed = await wallet_repository.find_by_id(
        workspace_id=contexts[0].workspace_id, wallet_id=first.id
    )
    assert refreshed is not None
    assert refreshed.balance_wei == 10**18
    assert refreshed.balance_block_number == 20_000_000
    assert not await wallet_repository.update_balance(
        workspace_id=contexts[0].workspace_id,
        wallet_id=first.id,
        balance_wei=0,
        block_number=19_999_999,
        refreshed_at=NOW,
    )

    async with database_sessions() as session, session.begin():
        await set_workspace_context(session, contexts[0].workspace_id)
        visible = set(await session.scalars(select(ExecutionWallet.id)))
        signer_table = await session.scalar(text("SELECT to_regclass('signer_key_envelopes')"))
    assert visible == {first.id}
    assert signer_table is None
