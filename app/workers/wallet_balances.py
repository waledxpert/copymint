"""Celery entrypoint for workspace-scoped Chainstack balance refreshes."""

import asyncio
from uuid import UUID

from app.application.wallets.balances import WalletBalanceService
from app.infrastructure.config import get_worker_settings
from app.infrastructure.db.repositories import SqlAlchemyWalletRepository
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.ethereum_rpc import ChainstackEthereumBalanceClient
from app.workers.celery_app import celery_app


async def _refresh_balance(*, workspace_id: UUID, wallet_id: UUID) -> bool:
    settings = get_worker_settings()
    engine = create_engine(settings)
    try:
        service = WalletBalanceService(
            SqlAlchemyWalletRepository(create_session_factory(engine)),
            ChainstackEthereumBalanceClient(
                endpoint=settings.chainstack_ethereum_http_url.get_secret_value(),
                chain_id=settings.ethereum_chain_id,
            ),
        )
        return await service.refresh(workspace_id=workspace_id, wallet_id=wallet_id)
    finally:
        await engine.dispose()


@celery_app.task(name="copymint.wallets.refresh_balance")  # type: ignore[untyped-decorator]
def refresh_balance(*, workspace_id: str, wallet_id: str) -> bool:
    return asyncio.run(_refresh_balance(workspace_id=UUID(workspace_id), wallet_id=UUID(wallet_id)))
