"""Workspace-scoped execution-wallet orchestration."""

import hashlib

import structlog
from web3 import Web3

from app.application.access.context import AccessError, RequestContext
from app.application.wallets.ports import (
    SignerWalletPort,
    SignerWalletResult,
    WalletBalanceRefreshPort,
    WalletRecord,
    WalletRepository,
)


class WalletLimitReached(AccessError):
    code = "wallet_limit_reached"


logger = structlog.get_logger(__name__)


def hash_idempotency_key(value: str) -> bytes:
    if not 16 <= len(value) <= 128:
        raise ValueError("idempotency key must contain between 16 and 128 characters")
    return hashlib.sha256(value.encode("utf-8")).digest()


class WalletService:
    def __init__(
        self,
        repository: WalletRepository,
        signer: SignerWalletPort,
        *,
        max_wallets_per_workspace: int,
        chain_id: int = 1,
        balance_refresh: WalletBalanceRefreshPort | None = None,
    ) -> None:
        if max_wallets_per_workspace < 1:
            raise ValueError("wallet limit must be positive")
        if chain_id != 1:
            raise ValueError("Release 1 supports Ethereum mainnet only")
        self._repository = repository
        self._signer = signer
        self._limit = max_wallets_per_workspace
        self._chain_id = chain_id
        self._balance_refresh = balance_refresh

    async def create_wallet(
        self, context: RequestContext, *, idempotency_key: str
    ) -> tuple[WalletRecord, bool]:
        workspace_id = context.require_workspace()
        if context.user_id is None:
            raise AccessError("An approved user identity is required.")
        key_hash = hash_idempotency_key(idempotency_key)
        existing = await self._repository.find_by_idempotency(
            workspace_id=workspace_id, idempotency_key_hash=key_hash
        )
        if existing is not None:
            return existing, False
        if await self._repository.count_active(workspace_id=workspace_id) >= self._limit:
            raise WalletLimitReached(
                f"This workspace has reached its limit of {self._limit} execution wallet(s)."
            )
        signer_result = await self._signer.create_wallet(
            workspace_id=workspace_id,
            chain_id=self._chain_id,
            idempotency_key=idempotency_key,
            correlation_id=context.correlation_id,
        )
        if signer_result.workspace_id != workspace_id or signer_result.chain_id != self._chain_id:
            raise RuntimeError("signer returned a mismatched wallet binding")
        checksum = Web3.to_checksum_address(signer_result.address)
        signer_result = SignerWalletResult(
            signer_key_id=signer_result.signer_key_id,
            workspace_id=signer_result.workspace_id,
            chain_id=signer_result.chain_id,
            address=checksum,
            created=signer_result.created,
        )
        return await self._repository.save_or_get(
            signer_result=signer_result,
            idempotency_key_hash=key_hash,
            actor_user_id=context.user_id,
            correlation_id=context.correlation_id,
        )

    async def list_wallets(self, context: RequestContext) -> list[WalletRecord]:
        workspace_id = context.require_workspace()
        wallets = await self._repository.list_wallets(workspace_id=workspace_id)
        if self._balance_refresh is not None:
            for wallet in wallets:
                try:
                    await self._balance_refresh.request_refresh(
                        workspace_id=workspace_id, wallet_id=wallet.id
                    )
                except Exception as exc:
                    logger.warning(
                        "wallet_balance_refresh_enqueue_failed",
                        workspace_id=str(workspace_id),
                        wallet_id=str(wallet.id),
                        error_type=type(exc).__name__,
                    )
        return wallets
