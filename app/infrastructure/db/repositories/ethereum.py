"""Atomic persistence of immutable mint evidence and scan checkpoints."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ethereum.decoders import DecodedMint, decode_mint_log
from app.application.ethereum.enrichment import enrich_mint
from app.application.ethereum.ports import EvmLog, EvmProvider, ProviderError
from app.application.ethereum.scanner import ScanBatch
from app.domain.enums import FinalityStatus, MintClassification, MintRoute
from app.domain.ids import uuid7
from app.infrastructure.db.models.ethereum import Collection, MintEvent, RawEvidence, ScanCheckpoint


def hex_bytes(value: str, *, length: int) -> bytes:
    try:
        result = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        raise ValueError("Ethereum hexadecimal value is malformed") from None
    if len(result) != length:
        raise ValueError(f"Ethereum value must contain {length} bytes")
    return result


def evidence_payload(log: EvmLog) -> dict[str, object]:
    values = {
        "address": log.address,
        "topics": list(log.topics),
        "data": log.data,
        "block_number": log.block_number,
        "block_hash": log.block_hash,
        "transaction_hash": log.transaction_hash,
        "log_index": log.log_index,
        "removed": log.removed,
    }
    return values


class SqlAlchemyMintBatchConsumer:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        collection_id: UUID,
        scan_version: int,
        provider_alias: str,
    ) -> None:
        self._sessions = sessions
        self._collection_id = collection_id
        self._scan_version = scan_version
        self._provider_alias = provider_alias

    async def commit(self, batch: ScanBatch) -> None:
        async with self._sessions() as session, session.begin():
            for log in batch.logs:
                payload = evidence_payload(log)
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                content_hash = hashlib.sha256(encoded).digest()
                evidence_id = uuid7()
                created = await session.scalar(
                    insert(RawEvidence)
                    .values(
                        id=evidence_id,
                        chain_id=1,
                        kind="log",
                        content_hash=content_hash,
                        provider_alias=self._provider_alias,
                        block_number=log.block_number,
                        transaction_hash=hex_bytes(log.transaction_hash, length=32),
                        payload=payload,
                        retention_status="active",
                        observed_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing(index_elements=[RawEvidence.content_hash])
                    .returning(RawEvidence.id)
                )
                if created is None:
                    created = await session.scalar(
                        select(RawEvidence.id).where(RawEvidence.content_hash == content_hash)
                    )
                if created is None:
                    raise RuntimeError("evidence idempotency conflict was not recoverable")
                for mint in decode_mint_log(log):
                    await session.execute(
                        insert(MintEvent)
                        .values(
                            id=uuid7(),
                            chain_id=1,
                            collection_id=self._collection_id,
                            raw_evidence_id=created,
                            block_number=mint.block_number,
                            block_hash=hex_bytes(mint.block_hash, length=32),
                            transaction_hash=hex_bytes(mint.transaction_hash, length=32),
                            log_index=mint.log_index,
                            sub_index=mint.sub_index,
                            token_standard=mint.token_standard,
                            token_id=mint.token_id,
                            quantity=mint.quantity,
                            recipient=mint.recipient,
                            operator=mint.operator,
                            identity_confidence=0,
                            identity_reason_code="not_enriched",
                            route=MintRoute.UNKNOWN,
                            classification=MintClassification.UNKNOWN_MINT,
                            classification_reason_code="not_classified",
                            finality=FinalityStatus.FINALIZED,
                            canonical=True,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[
                                MintEvent.chain_id,
                                MintEvent.transaction_hash,
                                MintEvent.log_index,
                                MintEvent.sub_index,
                            ]
                        )
                    )
            checkpoint = insert(ScanCheckpoint).values(
                id=uuid7(),
                collection_id=self._collection_id,
                scan_version=self._scan_version,
                last_committed_block_number=batch.end_block,
                last_committed_block_hash=hex_bytes(batch.end_block_hash, length=32),
            )
            await session.execute(
                checkpoint.on_conflict_do_update(
                    index_elements=[ScanCheckpoint.collection_id, ScanCheckpoint.scan_version],
                    set_={
                        "last_committed_block_number": (
                            checkpoint.excluded.last_committed_block_number
                        ),
                        "last_committed_block_hash": checkpoint.excluded.last_committed_block_hash,
                    },
                    where=(
                        checkpoint.excluded.last_committed_block_number
                        >= ScanCheckpoint.last_committed_block_number
                    ),
                )
            )


def transaction_payload(transaction: object) -> dict[str, object]:
    from app.application.ethereum.ports import EvmTransaction

    if not isinstance(transaction, EvmTransaction):
        raise TypeError("transaction evidence has an invalid type")
    return {
        "transaction_hash": transaction.transaction_hash,
        "sender": transaction.sender,
        "recipient": transaction.recipient,
        "value_wei": transaction.value_wei,
        "input_data": transaction.input_data,
        "block_number": transaction.block_number,
    }


def receipt_payload(receipt: object) -> dict[str, object]:
    from app.application.ethereum.ports import EvmReceipt

    if not isinstance(receipt, EvmReceipt):
        raise TypeError("receipt evidence has an invalid type")
    return {
        "transaction_hash": receipt.transaction_hash,
        "block_number": receipt.block_number,
        "block_hash": receipt.block_hash,
        "status": receipt.status,
        "gas_used": receipt.gas_used,
        "effective_gas_price": receipt.effective_gas_price,
    }


async def append_evidence(
    session: AsyncSession,
    *,
    kind: str,
    provider_alias: str,
    block_number: int,
    transaction_hash: str,
    payload: dict[str, object],
) -> None:
    encoded = json.dumps(
        {"kind": kind, "payload": payload}, sort_keys=True, separators=(",", ":")
    ).encode()
    await session.execute(
        insert(RawEvidence)
        .values(
            id=uuid7(),
            chain_id=1,
            kind=kind,
            content_hash=hashlib.sha256(encoded).digest(),
            provider_alias=provider_alias,
            block_number=block_number,
            transaction_hash=hex_bytes(transaction_hash, length=32),
            payload=payload,
            retention_status="active",
            observed_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(index_elements=[RawEvidence.content_hash])
    )


class SqlAlchemyMintEnricher:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        provider: EvmProvider,
        *,
        provider_alias: str,
    ) -> None:
        self._sessions = sessions
        self._provider = provider
        self._provider_alias = provider_alias

    async def enrich_range(
        self, *, collection_id: UUID, start_block: int, end_block: int
    ) -> tuple[str, ...]:
        async with self._sessions() as session:
            collection_address = await session.scalar(
                select(Collection.checksum_address).where(Collection.id == collection_id)
            )
            if collection_address is None:
                return ("collection_not_found",)
            hashes = list(
                await session.scalars(
                    select(MintEvent.transaction_hash)
                    .where(
                        MintEvent.collection_id == collection_id,
                        MintEvent.block_number.between(start_block, end_block),
                        MintEvent.identity_reason_code == "not_enriched",
                    )
                    .distinct()
                )
            )
        warnings: list[str] = []
        for raw_hash in hashes:
            transaction_hash = "0x" + raw_hash.hex()
            transaction = await self._provider.transaction(transaction_hash)
            receipt = await self._provider.receipt(transaction_hash)
            trace: dict[str, object] | None = None
            try:
                trace = await self._provider.trace_transaction(transaction_hash)
            except ProviderError as exc:
                warnings.append(f"trace_unavailable:{exc.code}")
            async with self._sessions() as session, session.begin():
                events = list(
                    await session.scalars(
                        select(MintEvent).where(
                            MintEvent.collection_id == collection_id,
                            MintEvent.transaction_hash == raw_hash,
                            MintEvent.identity_reason_code == "not_enriched",
                        )
                    )
                )
                await append_evidence(
                    session,
                    kind="transaction",
                    provider_alias=self._provider_alias,
                    block_number=transaction.block_number,
                    transaction_hash=transaction_hash,
                    payload=transaction_payload(transaction),
                )
                await append_evidence(
                    session,
                    kind="receipt",
                    provider_alias=self._provider_alias,
                    block_number=receipt.block_number,
                    transaction_hash=transaction_hash,
                    payload=receipt_payload(receipt),
                )
                if trace is not None:
                    await append_evidence(
                        session,
                        kind="trace",
                        provider_alias=self._provider_alias,
                        block_number=receipt.block_number,
                        transaction_hash=transaction_hash,
                        payload=trace,
                    )
                for event in events:
                    enriched = enrich_mint(
                        DecodedMint(
                            collection_address=collection_address,
                            token_standard=event.token_standard,
                            token_id=int(event.token_id),
                            quantity=int(event.quantity),
                            recipient=event.recipient,
                            operator=event.operator,
                            block_number=event.block_number,
                            block_hash="0x" + event.block_hash.hex(),
                            transaction_hash=transaction_hash,
                            log_index=event.log_index,
                            sub_index=event.sub_index,
                        ),
                        transaction,
                        receipt,
                    )
                    event.transaction_sender = enriched.transaction_sender
                    event.payer = enriched.payer
                    event.probable_initiator = enriched.probable_initiator
                    event.identity_confidence = enriched.identity_confidence
                    event.identity_reason_code = enriched.identity_reason_code
                    event.route = enriched.route
                    event.classification = enriched.classification
                    event.classification_reason_code = enriched.classification_reason_code
        return tuple(sorted(set(warnings)))
