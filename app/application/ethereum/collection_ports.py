"""Workspace collection records and queue boundaries."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.enums import CollectionScanStatus


@dataclass(frozen=True, slots=True)
class WorkspaceCollectionRecord:
    id: UUID
    collection_id: UUID
    workspace_id: UUID
    address: str
    label: str | None
    scan_status: CollectionScanStatus
    active: bool
    scan_start_block: int | None = None
    scan_end_block: int | None = None
    last_scanned_block: int | None = None
    quality_warning_codes: tuple[str, ...] = ()


class WorkspaceCollectionRepository(Protocol):
    async def add_or_get(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        address: str,
        label: str | None,
        correlation_id: UUID,
    ) -> tuple[WorkspaceCollectionRecord, bool]: ...

    async def list_collections(self, *, workspace_id: UUID) -> list[WorkspaceCollectionRecord]: ...

    async def find_by_address(
        self, *, workspace_id: UUID, address: str
    ) -> WorkspaceCollectionRecord | None: ...


class CollectionScanQueue(Protocol):
    async def request_scan(self, *, collection_id: UUID) -> None: ...
