"""Workspace-authorized Telegram scan progress notifications."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from aiogram import Bot
from sqlalchemy import select

from app.domain.enums import CollectionScanStatus
from app.infrastructure.config import get_notification_worker_settings
from app.infrastructure.db.models.access import NotificationDestination
from app.infrastructure.db.models.ethereum import (
    Collection,
    ScanCheckpoint,
    ScanJob,
    WorkspaceCollection,
)
from app.infrastructure.db.repositories.access import set_workspace_context
from app.infrastructure.db.session import create_engine, create_session_factory
from app.workers.notification_celery_app import notification_celery_app


@dataclass(frozen=True, slots=True)
class NotificationResult:
    terminal: bool


async def _notify(workspace_id: UUID, collection_id: UUID) -> NotificationResult:
    settings = get_notification_worker_settings()
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    try:
        async with sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            row = (
                await session.execute(
                    select(
                        WorkspaceCollection,
                        Collection,
                        ScanJob,
                        ScanCheckpoint,
                        NotificationDestination,
                    )
                    .join(Collection, Collection.id == WorkspaceCollection.collection_id)
                    .outerjoin(
                        ScanJob,
                        (ScanJob.collection_id == Collection.id) & (ScanJob.scan_version == 1),
                    )
                    .outerjoin(
                        ScanCheckpoint,
                        (ScanCheckpoint.collection_id == Collection.id)
                        & (ScanCheckpoint.scan_version == 1),
                    )
                    .join(
                        NotificationDestination,
                        NotificationDestination.workspace_id == WorkspaceCollection.workspace_id,
                    )
                    .where(
                        WorkspaceCollection.workspace_id == workspace_id,
                        WorkspaceCollection.collection_id == collection_id,
                        WorkspaceCollection.active.is_(True),
                        NotificationDestination.enabled.is_(True),
                        NotificationDestination.chat_type == "private",
                    )
                )
            ).first()
            if row is None:
                return NotificationResult(terminal=True)
            subscription, collection, job, checkpoint, destination = row
            terminal = collection.scan_status in {
                CollectionScanStatus.COMPLETE,
                CollectionScanStatus.FAILED,
                CollectionScanStatus.QUALITY_WARNING,
            }
            percent = 0
            warnings: tuple[str, ...] = ()
            if job is not None:
                position = (
                    checkpoint.last_committed_block_number
                    if checkpoint is not None
                    else job.start_block - 1
                )
                span = max(1, job.end_block - job.start_block + 1)
                percent = min(100, max(0, position - job.start_block + 1) * 100 // span)
                warnings = tuple(
                    str(item["code"])
                    for item in job.quality_warnings
                    if isinstance(item, dict) and isinstance(item.get("code"), str)
                )
            milestone = 100 if terminal else (percent // 25) * 25
            state = {
                "milestone": milestone,
                "status": collection.scan_status.value,
                "warnings": list(warnings),
            }
            if subscription.notification_settings.get("last_scan_report") == state:
                return NotificationResult(terminal=terminal)
            subscription.notification_settings = {
                **subscription.notification_settings,
                "last_scan_report": state,
            }
            label = f" ({subscription.label})" if subscription.label else ""
            message = (
                f"Collection scan {collection.scan_status.value}: {collection.checksum_address}"
                f"{label}\nProgress: {milestone}%"
            )
            if warnings:
                message += "\nQuality warning: " + ", ".join(warnings)
            chat_id = destination.telegram_chat_id
        await bot.send_message(chat_id, message)
        return NotificationResult(terminal=terminal)
    finally:
        await bot.session.close()
        await engine.dispose()


@notification_celery_app.task(name="copymint.collections.track_scan")  # type: ignore[untyped-decorator]
def track_scan(*, workspace_id: str, collection_id: str) -> bool:
    result = asyncio.run(_notify(UUID(workspace_id), UUID(collection_id)))
    if not result.terminal:
        notification_celery_app.send_task(
            "copymint.collections.track_scan",
            kwargs={"workspace_id": workspace_id, "collection_id": collection_id},
            queue="notifications",
            countdown=60,
        )
    return result.terminal
