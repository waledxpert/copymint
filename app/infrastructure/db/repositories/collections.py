"""Workspace-isolated collection registration persistence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ethereum.collection_ports import WorkspaceCollectionRecord
from app.domain.enums import (
    ActorType,
    CollectionScanStatus,
    DeploymentConfidence,
    Severity,
    TokenStandard,
)
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import AuditLog
from app.infrastructure.db.models.ethereum import (
    Collection,
    ScanCheckpoint,
    ScanJob,
    WorkspaceCollection,
)
from app.infrastructure.db.repositories.access import set_workspace_context


def collection_record(
    workspace_collection: WorkspaceCollection,
    collection: Collection,
    job: ScanJob | None = None,
    checkpoint: ScanCheckpoint | None = None,
) -> WorkspaceCollectionRecord:
    return WorkspaceCollectionRecord(
        id=workspace_collection.id,
        collection_id=collection.id,
        workspace_id=workspace_collection.workspace_id,
        address=collection.checksum_address,
        label=workspace_collection.label,
        scan_status=collection.scan_status,
        active=workspace_collection.active,
        scan_start_block=job.start_block if job is not None else None,
        scan_end_block=job.end_block if job is not None else None,
        last_scanned_block=(
            checkpoint.last_committed_block_number if checkpoint is not None else None
        ),
        quality_warning_codes=tuple(
            str(item["code"])
            for item in (job.quality_warnings if job is not None else [])
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        ),
    )


class SqlAlchemyWorkspaceCollectionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add_or_get(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: UUID,
        address: str,
        label: str | None,
        correlation_id: UUID,
    ) -> tuple[WorkspaceCollectionRecord, bool]:
        normalized = address.lower()
        collection_id = uuid7()
        subscription_id = uuid7()
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            collection = await session.scalar(
                insert(Collection)
                .values(
                    id=collection_id,
                    chain_id=1,
                    normalized_address=normalized,
                    checksum_address=address,
                    token_standard=TokenStandard.UNKNOWN,
                    deployment_confidence=DeploymentConfidence.UNKNOWN,
                    deployment_confidence_value=0,
                    scan_status=CollectionScanStatus.PENDING,
                )
                .on_conflict_do_nothing(
                    index_elements=[Collection.chain_id, Collection.normalized_address]
                )
                .returning(Collection)
            )
            if collection is None:
                collection = await session.scalar(
                    select(Collection).where(
                        Collection.chain_id == 1,
                        Collection.normalized_address == normalized,
                    )
                )
            if collection is None:
                raise RuntimeError("collection idempotency conflict was not recoverable")
            subscription = await session.scalar(
                insert(WorkspaceCollection)
                .values(
                    id=subscription_id,
                    workspace_id=workspace_id,
                    collection_id=collection.id,
                    label=label,
                    added_by_user_id=actor_user_id,
                    notification_settings={},
                    active=True,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        WorkspaceCollection.workspace_id,
                        WorkspaceCollection.collection_id,
                    ]
                )
                .returning(WorkspaceCollection)
            )
            created = subscription is not None
            if subscription is None:
                subscription = await session.scalar(
                    select(WorkspaceCollection).where(
                        WorkspaceCollection.workspace_id == workspace_id,
                        WorkspaceCollection.collection_id == collection.id,
                    )
                )
            if subscription is None:
                raise RuntimeError("collection subscription conflict was not recoverable")
            if created:
                session.add(
                    AuditLog(
                        workspace_id=workspace_id,
                        actor_type=ActorType.TELEGRAM_USER,
                        actor_id=str(actor_user_id),
                        action="workspace_collection_added",
                        resource_type="workspace_collection",
                        resource_id=str(subscription.id),
                        before=None,
                        after={"chain_id": 1, "address": address, "label": label},
                        correlation_id=correlation_id,
                        severity=Severity.INFO,
                    )
                )
            return collection_record(subscription, collection), created

    async def list_collections(self, *, workspace_id: UUID) -> list[WorkspaceCollectionRecord]:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            rows = (
                await session.execute(
                    select(WorkspaceCollection, Collection, ScanJob, ScanCheckpoint)
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
                    .where(
                        WorkspaceCollection.workspace_id == workspace_id,
                        WorkspaceCollection.active.is_(True),
                    )
                    .order_by(WorkspaceCollection.created_at.asc())
                )
            ).all()
            return [collection_record(*row) for row in rows]

    async def find_by_address(
        self, *, workspace_id: UUID, address: str
    ) -> WorkspaceCollectionRecord | None:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            row = (
                await session.execute(
                    select(WorkspaceCollection, Collection, ScanJob, ScanCheckpoint)
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
                    .where(
                        WorkspaceCollection.workspace_id == workspace_id,
                        WorkspaceCollection.active.is_(True),
                        Collection.chain_id == 1,
                        Collection.normalized_address == address.lower(),
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            return collection_record(*row)
