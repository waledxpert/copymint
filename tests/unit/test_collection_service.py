from uuid import UUID

import pytest

from app.application.access.context import RequestContext
from app.application.ethereum.collection_ports import WorkspaceCollectionRecord
from app.application.ethereum.collection_service import (
    CollectionNotFound,
    CollectionService,
    InvalidCollectionInput,
)
from app.domain.enums import CollectionScanStatus, WorkspaceRole
from app.domain.ids import uuid7

ADDRESS = "0x1111111111111111111111111111111111111111"


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


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[UUID, str], WorkspaceCollectionRecord] = {}

    async def add_or_get(self, **values: object) -> tuple[WorkspaceCollectionRecord, bool]:
        workspace_id = values["workspace_id"]
        address = values["address"]
        assert isinstance(workspace_id, UUID)
        assert isinstance(address, str)
        key = (workspace_id, address.lower())
        existing = self.records.get(key)
        if existing is not None:
            return existing, False
        record = WorkspaceCollectionRecord(
            id=uuid7(),
            collection_id=uuid7(),
            workspace_id=workspace_id,
            address=address,
            label=values["label"] if isinstance(values["label"], str) else None,
            scan_status=CollectionScanStatus.PENDING,
            active=True,
        )
        self.records[key] = record
        return record, True

    async def list_collections(self, *, workspace_id: UUID) -> list[WorkspaceCollectionRecord]:
        return [record for (scope, _), record in self.records.items() if scope == workspace_id]

    async def find_by_address(
        self, *, workspace_id: UUID, address: str
    ) -> WorkspaceCollectionRecord | None:
        return self.records.get((workspace_id, address.lower()))


class FakeQueue:
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    async def request_scan(self, *, workspace_id: UUID, collection_id: UUID) -> None:
        self.ids.append(collection_id)


async def test_collection_registration_is_idempotent_and_workspace_private() -> None:
    repository = FakeRepository()
    queue = FakeQueue()
    service = CollectionService(repository, queue)
    first_context = context()
    second_context = context()
    first = await service.add_collection(first_context, address=ADDRESS, label="  Alpha   Mint ")
    repeated = await service.add_collection(first_context, address=ADDRESS)
    second = await service.add_collection(second_context, address=ADDRESS)

    assert first.created
    assert not repeated.created
    assert second.created
    assert first.collection.label == "Alpha Mint"
    assert first.collection.id != second.collection.id
    assert await service.list_collections(first_context) == [first.collection]
    assert len(queue.ids) == 3


async def test_scan_requires_a_saved_collection_and_valid_address() -> None:
    service = CollectionService(FakeRepository(), FakeQueue())
    request_context = context()
    with pytest.raises(InvalidCollectionInput):
        await service.add_collection(request_context, address="not-an-address")
    with pytest.raises(CollectionNotFound):
        await service.request_scan(request_context, address=ADDRESS)
