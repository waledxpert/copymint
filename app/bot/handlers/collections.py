"""Workspace-private Ethereum collection Telegram commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.application.access.context import AccessError, RequestContext
from app.application.ethereum.collection_service import CollectionService
from app.bot.handlers.access import require_context


def command_arguments(message: Message) -> str:
    text = message.text or ""
    return text.partition(" ")[2].strip()


def build_collection_router() -> Router:
    router = Router(name="collections")

    @router.message(Command("add_collection"))
    async def add_collection_command(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        collection_service: CollectionService,
    ) -> None:
        arguments = command_arguments(message)
        if not arguments:
            await message.answer("Usage: /add_collection <Ethereum address> [private label]")
            return
        address, _, label = arguments.partition(" ")
        try:
            context = require_context(request_context, access_error)
            result = await collection_service.add_collection(
                context, address=address, label=label or None
            )
        except AccessError as exc:
            await message.answer(str(exc))
            return
        state = "saved" if result.created else "already saved"
        scan = "Scan queued." if result.scan_queued else "Saved, but scan queue is unavailable."
        await message.answer(
            f"Collection {state} for your workspace:\n"
            f"{result.collection.address}\n"
            f"{scan} Creating this entry does not mint an NFT or move funds."
        )

    @router.message(Command("scan"))
    async def scan_collection_command(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        collection_service: CollectionService,
    ) -> None:
        address = command_arguments(message)
        if not address:
            await message.answer("Usage: /scan <saved Ethereum collection address>")
            return
        try:
            context = require_context(request_context, access_error)
            collection, queued = await collection_service.request_scan(context, address=address)
        except AccessError as exc:
            await message.answer(str(exc))
            return
        if queued:
            await message.answer(f"Scan queued for {collection.address}.")
        else:
            await message.answer("The collection is saved, but the scan queue is unavailable.")

    @router.message(Command("collections"))
    async def list_collections_command(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        collection_service: CollectionService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            collections = await collection_service.list_collections(context)
        except AccessError as exc:
            await message.answer(str(exc))
            return
        if not collections:
            await message.answer("No collections saved. Use /add_collection to add one.")
            return
        lines = ["Your Ethereum collections:"]
        for index, collection in enumerate(collections, start=1):
            name = f" — {collection.label}" if collection.label else ""
            progress = ""
            if (
                collection.scan_start_block is not None
                and collection.scan_end_block is not None
                and collection.last_scanned_block is not None
            ):
                span = max(1, collection.scan_end_block - collection.scan_start_block + 1)
                covered = max(0, collection.last_scanned_block - collection.scan_start_block + 1)
                progress = f" ({min(100, covered * 100 // span)}%)"
            lines.append(
                f"{index}. {collection.address}{name}\n"
                f"   Scan: {collection.scan_status.value}{progress}"
            )
            if collection.quality_warning_codes:
                lines.append("   Quality warning: " + ", ".join(collection.quality_warning_codes))
        await message.answer("\n".join(lines))

    return router
