"""Balance-refresh queue adapter that contains no provider credential."""

import asyncio
from uuid import UUID

from celery import Celery


class CeleryWalletBalanceRefreshQueue:
    def __init__(self, *, broker_url: str) -> None:
        self._client = Celery("copymint-api-producer", broker=broker_url)

    async def request_refresh(self, *, workspace_id: UUID, wallet_id: UUID) -> None:
        await asyncio.to_thread(
            self._client.send_task,
            "copymint.wallets.refresh_balance",
            kwargs={"workspace_id": str(workspace_id), "wallet_id": str(wallet_id)},
            queue="indexer",
        )
