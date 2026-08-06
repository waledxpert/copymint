from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from app.application.access.context import RequestContext
from app.application.ethereum.collection_ports import WorkspaceCollectionRecord
from app.application.ethereum.collection_service import CollectionRegistrationResult
from app.bot.handlers.collections import build_collection_router
from app.domain.enums import CollectionScanStatus, WorkspaceRole
from app.domain.ids import uuid7

ADDRESS = "0x1111111111111111111111111111111111111111"


def handler(router: Any, name: str) -> Any:
    return next(item.callback for item in router.message.handlers if item.callback.__name__ == name)


def context() -> RequestContext:
    return RequestContext(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        correlation_id=uuid7(),
        user_id=uuid7(),
        workspace_id=uuid7(),
        workspace_role=WorkspaceRole.OWNER,
    )


@dataclass
class FakeMessage:
    text: str
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.answers.append(text)


class FakeService:
    def __init__(self, request_context: RequestContext) -> None:
        self.collection = WorkspaceCollectionRecord(
            id=uuid7(),
            collection_id=uuid7(),
            workspace_id=request_context.workspace_id,  # type: ignore[arg-type]
            address=ADDRESS,
            label="Alpha",
            scan_status=CollectionScanStatus.PENDING,
            active=True,
        )

    async def add_collection(self, *args: Any, **kwargs: Any) -> CollectionRegistrationResult:
        return CollectionRegistrationResult(self.collection, True, True)

    async def request_scan(
        self, *args: Any, **kwargs: Any
    ) -> tuple[WorkspaceCollectionRecord, bool]:
        return self.collection, True

    async def list_collections(self, *args: Any, **kwargs: Any) -> list[WorkspaceCollectionRecord]:
        return [self.collection]


async def test_add_scan_and_list_collection_commands_are_clear_and_non_executing() -> None:
    router = build_collection_router()
    request_context = context()
    service = FakeService(request_context)
    add_message = FakeMessage(f"/add_collection {ADDRESS} Alpha")
    await handler(router, "add_collection_command")(add_message, request_context, None, service)
    assert "Scan queued" in add_message.answers[0]
    assert "does not mint an NFT or move funds" in add_message.answers[0]

    scan_message = FakeMessage(f"/scan {ADDRESS}")
    await handler(router, "scan_collection_command")(scan_message, request_context, None, service)
    assert scan_message.answers == [f"Scan queued for {ADDRESS}."]

    list_message = FakeMessage("/collections")
    await handler(router, "list_collections_command")(list_message, request_context, None, service)
    assert "Alpha" in list_message.answers[0]
    assert "pending" in list_message.answers[0]


async def test_add_collection_usage_does_not_call_service() -> None:
    router = build_collection_router()
    message = FakeMessage("/add_collection")
    await handler(router, "add_collection_command")(message, None, None, SimpleNamespace())
    assert message.answers == ["Usage: /add_collection <Ethereum address> [private label]"]
