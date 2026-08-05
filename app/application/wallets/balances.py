"""Refresh a single workspace-bound wallet balance at a pinned Ethereum block."""

from datetime import UTC, datetime
from uuid import UUID

from app.application.wallets.ports import EthereumBalancePort, WalletRepository


class WalletBalanceService:
    def __init__(self, repository: WalletRepository, ethereum: EthereumBalancePort) -> None:
        self._repository = repository
        self._ethereum = ethereum

    async def refresh(self, *, workspace_id: UUID, wallet_id: UUID) -> bool:
        wallet = await self._repository.find_by_id(workspace_id=workspace_id, wallet_id=wallet_id)
        if wallet is None:
            return False
        balance_wei, block_number = await self._ethereum.balance_at_latest_block(
            address=wallet.address
        )
        return await self._repository.update_balance(
            workspace_id=workspace_id,
            wallet_id=wallet_id,
            balance_wei=balance_wei,
            block_number=block_number,
            refreshed_at=datetime.now(UTC),
        )
