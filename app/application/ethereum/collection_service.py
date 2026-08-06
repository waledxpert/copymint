"""Workspace-scoped collection registration and scan orchestration."""

from dataclasses import dataclass
from uuid import UUID

from web3 import Web3

from app.application.access.context import AccessError, RequestContext
from app.application.ethereum.collection_ports import (
    CollectionScanQueue,
    WorkspaceCollectionRecord,
    WorkspaceCollectionRepository,
)


class InvalidCollectionInput(AccessError):
    code = "invalid_collection_input"


class CollectionNotFound(AccessError):
    code = "collection_not_found"


@dataclass(frozen=True, slots=True)
class CollectionRegistrationResult:
    collection: WorkspaceCollectionRecord
    created: bool
    scan_queued: bool


class CollectionService:
    def __init__(
        self,
        repository: WorkspaceCollectionRepository,
        scan_queue: CollectionScanQueue,
    ) -> None:
        self._repository = repository
        self._scan_queue = scan_queue

    @staticmethod
    def normalize_address(address: str) -> str:
        if not Web3.is_address(address):
            raise InvalidCollectionInput("Provide a valid Ethereum contract address.")
        return Web3.to_checksum_address(address)

    @staticmethod
    def normalize_label(label: str | None) -> str | None:
        if label is None:
            return None
        normalized = " ".join(label.split())
        if not normalized:
            return None
        if len(normalized) > 120:
            raise InvalidCollectionInput("Collection labels cannot exceed 120 characters.")
        return normalized

    async def add_collection(
        self,
        context: RequestContext,
        *,
        address: str,
        label: str | None = None,
    ) -> CollectionRegistrationResult:
        workspace_id = context.require_workspace()
        if context.user_id is None:
            raise AccessError("An approved user identity is required.")
        collection, created = await self._repository.add_or_get(
            workspace_id=workspace_id,
            actor_user_id=context.user_id,
            address=self.normalize_address(address),
            label=self.normalize_label(label),
            correlation_id=context.correlation_id,
        )
        queued = await self._queue(workspace_id, collection.collection_id)
        return CollectionRegistrationResult(collection, created, queued)

    async def request_scan(
        self, context: RequestContext, *, address: str
    ) -> tuple[WorkspaceCollectionRecord, bool]:
        workspace_id = context.require_workspace()
        checksum = self.normalize_address(address)
        collection = await self._repository.find_by_address(
            workspace_id=workspace_id, address=checksum
        )
        if collection is None:
            raise CollectionNotFound(
                "That collection is not saved in your workspace. Use /add_collection first."
            )
        return collection, await self._queue(workspace_id, collection.collection_id)

    async def list_collections(self, context: RequestContext) -> list[WorkspaceCollectionRecord]:
        return await self._repository.list_collections(workspace_id=context.require_workspace())

    async def _queue(self, workspace_id: UUID, collection_id: UUID) -> bool:
        try:
            await self._scan_queue.request_scan(
                workspace_id=workspace_id, collection_id=collection_id
            )
        except Exception:
            return False
        return True
