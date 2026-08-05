"""Ports and safe application records for execution wallets."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.enums import WalletStatus


@dataclass(frozen=True, slots=True)
class WalletRecord:
    id: UUID
    workspace_id: UUID
    chain_id: int
    address: str
    signer_key_id: UUID
    status: WalletStatus
    balance_wei: int
    balance_block_number: int | None = None
    balance_refreshed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SignerWalletResult:
    signer_key_id: UUID
    workspace_id: UUID
    chain_id: int
    address: str
    created: bool


class WalletRepository(Protocol):
    async def find_by_idempotency(
        self, *, workspace_id: UUID, idempotency_key_hash: bytes
    ) -> WalletRecord | None: ...

    async def count_active(self, *, workspace_id: UUID) -> int: ...

    async def save_or_get(
        self,
        *,
        signer_result: SignerWalletResult,
        idempotency_key_hash: bytes,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> tuple[WalletRecord, bool]: ...

    async def list_wallets(self, *, workspace_id: UUID) -> list[WalletRecord]: ...

    async def find_by_id(self, *, workspace_id: UUID, wallet_id: UUID) -> WalletRecord | None: ...

    async def update_balance(
        self,
        *,
        workspace_id: UUID,
        wallet_id: UUID,
        balance_wei: int,
        block_number: int,
        refreshed_at: datetime,
    ) -> bool: ...


class SignerWalletPort(Protocol):
    async def create_wallet(
        self,
        *,
        workspace_id: UUID,
        chain_id: int,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> SignerWalletResult: ...


class WalletBalanceRefreshPort(Protocol):
    async def request_refresh(self, *, workspace_id: UUID, wallet_id: UUID) -> None: ...


class EthereumBalancePort(Protocol):
    async def balance_at_latest_block(self, *, address: str) -> tuple[int, int]: ...
