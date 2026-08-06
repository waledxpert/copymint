"""Opaque global collection-scan job publisher for the API process."""

import asyncio
from uuid import UUID

from celery import Celery


class CeleryCollectionScanQueue:
    def __init__(self, *, broker_url: str) -> None:
        self._client = Celery("copymint-api-producer", broker=broker_url)

    async def request_scan(self, *, workspace_id: UUID, collection_id: UUID) -> None:
        await asyncio.to_thread(
            self._client.send_task,
            "copymint.ethereum.scan_collection",
            kwargs={"collection_id": str(collection_id)},
            queue="indexer",
        )
        await asyncio.to_thread(
            self._client.send_task,
            "copymint.collections.track_scan",
            kwargs={"workspace_id": str(workspace_id), "collection_id": str(collection_id)},
            queue="notifications",
        )
