from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ethereum.decoders import ERC721_TRANSFER_TOPIC
from app.application.ethereum.ports import (
    BlockReference,
    EvmLog,
    EvmReceipt,
    EvmTransaction,
    ProviderError,
)
from app.application.ethereum.scanner import ScanBatch
from app.domain.enums import (
    CollectionScanStatus,
    DeploymentConfidence,
    EvidenceKind,
    EvidenceRetentionStatus,
    FinalityStatus,
    MintClassification,
    MintRoute,
    TokenStandard,
)
from app.domain.ids import uuid7
from app.infrastructure.db.models.ethereum import (
    Chain,
    Collection,
    MintEvent,
    RawEvidence,
    ScanCheckpoint,
)
from app.infrastructure.db.repositories.ethereum import (
    SqlAlchemyMintBatchConsumer,
    SqlAlchemyMintEnricher,
)

pytestmark = pytest.mark.database


class EnrichmentProvider:
    alias = "fixture-enrichment"

    async def chain_id(self) -> int:
        return 1

    async def block(self, tag: int | str) -> BlockReference:
        raise NotImplementedError

    async def code(self, address: str, block: int | str = "latest") -> bytes:
        raise NotImplementedError

    async def storage_at(self, address: str, slot: str, block: int | str) -> bytes:
        raise NotImplementedError

    async def logs(self, **values: object) -> list[EvmLog]:
        raise NotImplementedError

    async def transaction(self, transaction_hash: str) -> EvmTransaction:
        return EvmTransaction(
            transaction_hash=transaction_hash,
            sender="0x" + "bb" * 20,
            recipient="0x" + "77" * 20,
            value_wei=10**18,
            input_data="0x12345678",
            block_number=120,
        )

    async def receipt(self, transaction_hash: str) -> EvmReceipt:
        return EvmReceipt(
            transaction_hash=transaction_hash,
            block_number=120,
            block_hash="0x" + "99" * 32,
            status=1,
            gas_used=100_000,
            effective_gas_price=1_000_000_000,
        )

    async def trace_transaction(self, transaction_hash: str) -> dict[str, object]:
        raise ProviderError("http_403", transient=False)


@pytest.mark.asyncio
async def test_global_ethereum_schema_seeds_mainnet_and_enforces_event_identity(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    collection_id = uuid7()
    evidence_id = uuid7()
    transaction_hash = bytes.fromhex("11" * 32)
    async with database_sessions() as session, session.begin():
        chain = await session.get(Chain, 1)
        assert chain is not None
        assert chain.namespace == "eip155"
        session.add(
            Collection(
                id=collection_id,
                chain_id=1,
                normalized_address="0x" + "22" * 20,
                checksum_address="0x" + "22" * 20,
                token_standard=TokenStandard.ERC721,
                deployment_block_number=100,
                deployment_block_hash=bytes.fromhex("33" * 32),
                deployment_confidence=DeploymentConfidence.EXACT,
                deployment_confidence_value=100,
                scan_status=CollectionScanStatus.PENDING,
            )
        )
        session.add(
            RawEvidence(
                id=evidence_id,
                chain_id=1,
                kind=EvidenceKind.LOG,
                content_hash=bytes.fromhex("44" * 32),
                provider_alias="fixture",
                block_number=101,
                transaction_hash=transaction_hash,
                payload={"removed": False},
                retention_status=EvidenceRetentionStatus.ACTIVE,
                observed_at=datetime(2026, 8, 6, tzinfo=UTC),
            )
        )
    values = {
        "chain_id": 1,
        "collection_id": collection_id,
        "raw_evidence_id": evidence_id,
        "block_number": 101,
        "block_hash": bytes.fromhex("55" * 32),
        "transaction_hash": transaction_hash,
        "log_index": 2,
        "sub_index": 0,
        "token_standard": TokenStandard.ERC721,
        "token_id": Decimal(7),
        "quantity": Decimal(1),
        "recipient": "0x" + "66" * 20,
        "identity_confidence": 0,
        "identity_reason_code": "not_enriched",
        "route": MintRoute.UNKNOWN,
        "classification": MintClassification.UNKNOWN_MINT,
        "classification_reason_code": "not_classified",
        "finality": FinalityStatus.FINALIZED,
        "canonical": True,
    }
    async with database_sessions() as session, session.begin():
        session.add(MintEvent(id=uuid7(), **values))
    with pytest.raises(IntegrityError):
        async with database_sessions() as session, session.begin():
            session.add(MintEvent(id=uuid7(), **values))
    async with database_sessions() as session:
        events = list(await session.scalars(select(MintEvent)))
    assert len(events) == 1
    with pytest.raises(DBAPIError, match="raw evidence is immutable"):
        async with database_sessions() as session, session.begin():
            await session.execute(
                update(RawEvidence)
                .where(RawEvidence.id == evidence_id)
                .values(payload={"tampered": True})
            )


@pytest.mark.asyncio
async def test_batch_persistence_and_checkpoint_are_atomic_and_idempotent(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    collection_id = uuid7()
    async with database_sessions() as session, session.begin():
        session.add(
            Collection(
                id=collection_id,
                chain_id=1,
                normalized_address="0x" + "77" * 20,
                checksum_address="0x" + "77" * 20,
                token_standard=TokenStandard.ERC721,
                deployment_confidence=DeploymentConfidence.UNKNOWN,
                deployment_confidence_value=0,
                scan_status=CollectionScanStatus.SCANNING,
            )
        )
    event = EvmLog(
        address="0x" + "77" * 20,
        topics=(
            ERC721_TRANSFER_TOPIC,
            "0x" + "00" * 32,
            "0x" + "00" * 12 + "88" * 20,
            "0x" + (9).to_bytes(32, "big").hex(),
        ),
        data="0x",
        block_number=120,
        block_hash="0x" + "99" * 32,
        transaction_hash="0x" + "aa" * 32,
        log_index=4,
        removed=False,
    )
    batch = ScanBatch(120, 120, "0x" + "99" * 32, (event,))
    consumer = SqlAlchemyMintBatchConsumer(
        database_sessions,
        collection_id=collection_id,
        scan_version=1,
        provider_alias="fixture",
    )
    await consumer.commit(batch)
    await consumer.commit(batch)
    async with database_sessions() as session:
        assert len(list(await session.scalars(select(RawEvidence)))) == 1
        assert len(list(await session.scalars(select(MintEvent)))) == 1
        checkpoint = await session.scalar(select(ScanCheckpoint))
    assert checkpoint is not None
    assert checkpoint.last_committed_block_number == 120
    assert checkpoint.last_committed_block_hash == bytes.fromhex("99" * 32)

    enricher = SqlAlchemyMintEnricher(
        database_sessions,
        EnrichmentProvider(),
        provider_alias="fixture-enrichment",
    )
    warnings = await enricher.enrich_range(
        collection_id=collection_id, start_block=120, end_block=120
    )
    assert warnings == ("trace_unavailable:http_403",)
    assert (
        await enricher.enrich_range(collection_id=collection_id, start_block=120, end_block=120)
        == ()
    )
    async with database_sessions() as session:
        enriched = await session.scalar(select(MintEvent))
        evidence_kinds = set(await session.scalars(select(RawEvidence.kind)))
    assert enriched is not None
    assert enriched.transaction_sender == "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"
    assert enriched.probable_initiator == enriched.transaction_sender
    assert enriched.identity_confidence == 85
    assert enriched.identity_reason_code == "direct_transaction_sender"
    assert enriched.route is MintRoute.DIRECT
    assert enriched.classification is MintClassification.UNKNOWN_MINT
    assert evidence_kinds == {EvidenceKind.LOG, EvidenceKind.TRANSACTION, EvidenceKind.RECEIPT}
