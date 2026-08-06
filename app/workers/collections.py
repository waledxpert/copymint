"""Resumable global Ethereum collection validation and historical scanning."""

import asyncio
import platform
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from app.application.ethereum.collections import EthereumCollectionDiscovery
from app.application.ethereum.scanner import AdaptiveHistoricalScanner
from app.domain.enums import CollectionScanStatus, ScanJobStatus
from app.domain.ids import uuid7
from app.infrastructure.config import get_worker_settings
from app.infrastructure.db.models.ethereum import Collection, ScanCheckpoint, ScanJob
from app.infrastructure.db.repositories.ethereum import (
    SqlAlchemyMintBatchConsumer,
    SqlAlchemyMintEnricher,
)
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.ethereum import JsonRpcEvmProvider
from app.workers.celery_app import celery_app

SCAN_SLICE_BLOCKS = 100


@dataclass(frozen=True, slots=True)
class ScanSliceResult:
    completed: bool


async def _scan_collection(collection_id: UUID) -> ScanSliceResult:
    settings = get_worker_settings()
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    provider = JsonRpcEvmProvider(endpoint=settings.chainstack_ethereum_http_url.get_secret_value())
    try:
        async with sessions() as session:
            collection = await session.get(Collection, collection_id)
        if collection is None:
            return ScanSliceResult(completed=True)
        finalized = await provider.block("finalized")
        if collection.deployment_block_number is None:
            probe = await EthereumCollectionDiscovery(provider).probe(collection.checksum_address)
            async with sessions() as session, session.begin():
                current = await session.get(Collection, collection_id, with_for_update=True)
                if current is None:
                    return ScanSliceResult(completed=True)
                current.deployment_block_number = probe.deployment_block_number
                current.deployment_block_hash = bytes.fromhex(
                    probe.deployment_block_hash.removeprefix("0x")
                )
                current.deployment_confidence = probe.deployment_confidence
                current.deployment_confidence_value = probe.deployment_confidence_value
                current.scan_status = CollectionScanStatus.SCANNING
            start_block = probe.deployment_block_number
        else:
            start_block = collection.deployment_block_number

        async with sessions() as session, session.begin():
            job = await session.scalar(
                select(ScanJob).where(
                    ScanJob.collection_id == collection_id,
                    ScanJob.scan_version == 1,
                )
            )
            if job is None:
                job = ScanJob(
                    id=uuid7(),
                    collection_id=collection_id,
                    scan_version=1,
                    start_block=start_block,
                    end_block=finalized.number,
                    status=ScanJobStatus.RUNNING,
                    attempt_count=1,
                    quality_warnings=[],
                )
                session.add(job)
                await session.flush()
            elif job.status is ScanJobStatus.COMPLETED:
                return ScanSliceResult(completed=True)
            else:
                job.status = ScanJobStatus.RUNNING
                job.attempt_count += 1
            checkpoint = await session.scalar(
                select(ScanCheckpoint).where(
                    ScanCheckpoint.collection_id == collection_id,
                    ScanCheckpoint.scan_version == 1,
                )
            )
            cursor = (
                checkpoint.last_committed_block_number + 1
                if checkpoint is not None
                else job.start_block
            )
            fixed_end = job.end_block

        if cursor <= fixed_end:
            slice_end = min(cursor + SCAN_SLICE_BLOCKS - 1, fixed_end)
            scanner = AdaptiveHistoricalScanner(
                provider,
                initial_chunk=min(settings.indexer_initial_chunk, SCAN_SLICE_BLOCKS),
                maximum_chunk=min(settings.indexer_max_chunk, SCAN_SLICE_BLOCKS),
            )
            await scanner.scan(
                address=collection.checksum_address,
                start_block=cursor,
                end_block=slice_end,
                consumer=SqlAlchemyMintBatchConsumer(
                    sessions,
                    collection_id=collection_id,
                    scan_version=1,
                    provider_alias=provider.alias,
                ),
            )
            quality_warnings = await SqlAlchemyMintEnricher(
                sessions,
                provider,
                provider_alias=provider.alias,
            ).enrich_range(
                collection_id=collection_id,
                start_block=cursor,
                end_block=slice_end,
            )
            if quality_warnings:
                async with sessions() as session, session.begin():
                    job = await session.scalar(
                        select(ScanJob).where(
                            ScanJob.collection_id == collection_id,
                            ScanJob.scan_version == 1,
                        )
                    )
                    if job is not None:
                        existing = {
                            str(item.get("code"))
                            for item in job.quality_warnings
                            if isinstance(item, dict)
                        }
                        job.quality_warnings = [
                            *job.quality_warnings,
                            *[
                                {"code": warning}
                                for warning in quality_warnings
                                if warning not in existing
                            ],
                        ]
        completed = cursor > fixed_end or slice_end >= fixed_end
        if completed:
            async with sessions() as session, session.begin():
                job = await session.scalar(
                    select(ScanJob).where(
                        ScanJob.collection_id == collection_id,
                        ScanJob.scan_version == 1,
                    )
                )
                current = await session.get(Collection, collection_id)
                if job is not None:
                    job.status = ScanJobStatus.COMPLETED
                if current is not None:
                    current.scan_status = (
                        CollectionScanStatus.QUALITY_WARNING
                        if job is not None and job.quality_warnings
                        else CollectionScanStatus.COMPLETE
                    )
        return ScanSliceResult(completed=completed)
    finally:
        await engine.dispose()


def run_scan(collection_id: UUID) -> ScanSliceResult:
    if platform.system() == "Windows":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(_scan_collection(collection_id))
    return asyncio.run(_scan_collection(collection_id))


@celery_app.task(name="copymint.ethereum.scan_collection")  # type: ignore[untyped-decorator]
def scan_collection(*, collection_id: str) -> bool:
    parsed = UUID(collection_id)
    result = run_scan(parsed)
    if not result.completed:
        celery_app.send_task(
            "copymint.ethereum.scan_collection",
            kwargs={"collection_id": collection_id},
            queue="indexer",
        )
    return result.completed
