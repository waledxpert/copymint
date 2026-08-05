from datetime import datetime
from uuid import UUID

import pytest

from app.application.wallets.balances import WalletBalanceService
from app.application.wallets.ports import WalletRecord
from app.domain.enums import WalletStatus
from app.domain.ids import uuid7


class FakeRepository:
    def __init__(self, wallet: WalletRecord | None) -> None:
        self.wallet = wallet
        self.updated: dict[str, object] | None = None

    async def find_by_id(self, *, workspace_id: UUID, wallet_id: UUID) -> WalletRecord | None:
        if self.wallet and self.wallet.workspace_id == workspace_id and self.wallet.id == wallet_id:
            return self.wallet
        return None

    async def update_balance(self, **values: object) -> bool:
        assert isinstance(values["refreshed_at"], datetime)
        self.updated = values
        return True


class FakeEthereum:
    async def balance_at_latest_block(self, *, address: str) -> tuple[int, int]:
        return 123, 456


@pytest.mark.asyncio
async def test_refresh_updates_only_a_workspace_bound_wallet() -> None:
    workspace_id = uuid7()
    wallet = WalletRecord(
        id=uuid7(),
        workspace_id=workspace_id,
        chain_id=1,
        address="0x1111111111111111111111111111111111111111",
        signer_key_id=uuid7(),
        status=WalletStatus.ACTIVE,
        balance_wei=0,
    )
    repository = FakeRepository(wallet)
    service = WalletBalanceService(repository, FakeEthereum())  # type: ignore[arg-type]
    assert await service.refresh(workspace_id=workspace_id, wallet_id=wallet.id)
    assert repository.updated is not None
    assert repository.updated["balance_wei"] == 123
    assert repository.updated["block_number"] == 456

    repository.updated = None
    assert not await service.refresh(workspace_id=uuid7(), wallet_id=wallet.id)
    assert repository.updated is None
