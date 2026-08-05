from uuid import UUID

import pytest

from app.application.access.context import RequestContext
from app.application.wallets.ports import SignerWalletResult, WalletRecord
from app.application.wallets.service import WalletLimitReached, WalletService
from app.domain.enums import WalletStatus, WorkspaceRole
from app.domain.ids import uuid7


class FakeWalletRepository:
    def __init__(self) -> None:
        self.wallets: list[tuple[WalletRecord, bytes]] = []

    async def find_by_idempotency(
        self, *, workspace_id: UUID, idempotency_key_hash: bytes
    ) -> WalletRecord | None:
        return next(
            (
                wallet
                for wallet, key_hash in self.wallets
                if wallet.workspace_id == workspace_id and key_hash == idempotency_key_hash
            ),
            None,
        )

    async def count_active(self, *, workspace_id: UUID) -> int:
        return sum(
            wallet.workspace_id == workspace_id and wallet.status is WalletStatus.ACTIVE
            for wallet, _ in self.wallets
        )

    async def save_or_get(self, **values: object) -> tuple[WalletRecord, bool]:
        signer = values["signer_result"]
        assert isinstance(signer, SignerWalletResult)
        key_hash = values["idempotency_key_hash"]
        assert isinstance(key_hash, bytes)
        existing = await self.find_by_idempotency(
            workspace_id=signer.workspace_id, idempotency_key_hash=key_hash
        )
        if existing:
            return existing, False
        wallet = WalletRecord(
            id=uuid7(),
            workspace_id=signer.workspace_id,
            chain_id=signer.chain_id,
            address=signer.address,
            signer_key_id=signer.signer_key_id,
            status=WalletStatus.ACTIVE,
            balance_wei=0,
        )
        self.wallets.append((wallet, key_hash))
        return wallet, True

    async def list_wallets(self, *, workspace_id: UUID) -> list[WalletRecord]:
        return [wallet for wallet, _ in self.wallets if wallet.workspace_id == workspace_id]


class FakeSigner:
    def __init__(self) -> None:
        self.calls = 0
        self.workspace_override: UUID | None = None

    async def create_wallet(self, **values: object) -> SignerWalletResult:
        self.calls += 1
        workspace_id = values["workspace_id"]
        assert isinstance(workspace_id, UUID)
        return SignerWalletResult(
            signer_key_id=uuid7(),
            workspace_id=self.workspace_override or workspace_id,
            chain_id=1,
            address="0x1111111111111111111111111111111111111111",
            created=True,
        )


class FakeRefreshQueue:
    def __init__(self) -> None:
        self.wallet_ids: list[UUID] = []

    async def request_refresh(self, *, workspace_id: UUID, wallet_id: UUID) -> None:
        self.wallet_ids.append(wallet_id)


def context(workspace_id: UUID | None = None) -> RequestContext:
    return RequestContext(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        correlation_id=uuid7(),
        user_id=uuid7(),
        workspace_id=workspace_id or uuid7(),
        workspace_role=WorkspaceRole.OWNER,
    )


@pytest.mark.asyncio
async def test_wallet_creation_is_idempotent_before_limit_check() -> None:
    repository = FakeWalletRepository()
    signer = FakeSigner()
    service = WalletService(
        repository,
        signer,
        max_wallets_per_workspace=1,  # type: ignore[arg-type]
    )
    request_context = context()
    first, created = await service.create_wallet(
        request_context, idempotency_key="wallet-request-001"
    )
    repeated, repeated_created = await service.create_wallet(
        request_context, idempotency_key="wallet-request-001"
    )

    assert created
    assert not repeated_created
    assert repeated.id == first.id
    assert signer.calls == 1
    with pytest.raises(WalletLimitReached):
        await service.create_wallet(request_context, idempotency_key="wallet-request-002")


@pytest.mark.asyncio
async def test_wallet_service_rejects_mismatched_signer_binding() -> None:
    signer = FakeSigner()
    signer.workspace_override = uuid7()
    service = WalletService(
        FakeWalletRepository(),
        signer,
        max_wallets_per_workspace=1,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="mismatched"):
        await service.create_wallet(context(), idempotency_key="wallet-request-003")


@pytest.mark.asyncio
async def test_listing_requests_workspace_scoped_balance_refresh() -> None:
    repository = FakeWalletRepository()
    signer = FakeSigner()
    refresh = FakeRefreshQueue()
    service = WalletService(
        repository,  # type: ignore[arg-type]
        signer,
        max_wallets_per_workspace=1,
        balance_refresh=refresh,
    )
    request_context = context()
    wallet, _ = await service.create_wallet(request_context, idempotency_key="wallet-request-004")
    assert await service.list_wallets(request_context) == [wallet]
    assert refresh.wallet_ids == [wallet.id]
