from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.access.context import TelegramIdentity
from app.application.access.service import AccessService
from app.application.ethereum.collection_service import CollectionService
from app.infrastructure.db.repositories.access import SqlAlchemyAccessRepository
from app.infrastructure.db.repositories.collections import (
    SqlAlchemyWorkspaceCollectionRepository,
)

pytestmark = pytest.mark.database
NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
ADDRESS = "0x1111111111111111111111111111111111111111"


def identity(user_id: int) -> TelegramIdentity:
    return TelegramIdentity(user_id, user_id, "private", username=f"user{user_id}")


class RecordingQueue:
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    async def request_scan(self, *, collection_id: UUID) -> None:
        self.ids.append(collection_id)


async def test_workspace_collection_registration_is_private_and_globally_deduplicated(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    access = AccessService(
        SqlAlchemyAccessRepository(database_sessions),
        platform_owner_ids=frozenset({1}),
        clock=lambda: NOW,
    )
    owner = await access.resolve_context(identity(1))
    contexts = []
    for telegram_user_id in (99, 100):
        request = await access.request_access(identity(telegram_user_id))
        assert request.request_id is not None
        await access.approve(owner, request.request_id)
        contexts.append(await access.resolve_context(identity(telegram_user_id)))

    queue = RecordingQueue()
    service = CollectionService(SqlAlchemyWorkspaceCollectionRepository(database_sessions), queue)
    first = await service.add_collection(contexts[0], address=ADDRESS, label="Private Alpha")
    repeated = await service.add_collection(contexts[0], address=ADDRESS)
    second = await service.add_collection(contexts[1], address=ADDRESS, label="Private Beta")

    assert first.created and not repeated.created and second.created
    assert first.collection.collection_id == second.collection.collection_id
    assert first.collection.id != second.collection.id
    assert [item.label for item in await service.list_collections(contexts[0])] == ["Private Alpha"]
    assert [item.label for item in await service.list_collections(contexts[1])] == ["Private Beta"]
    assert queue.ids == [
        first.collection.collection_id,
        first.collection.collection_id,
        second.collection.collection_id,
    ]
