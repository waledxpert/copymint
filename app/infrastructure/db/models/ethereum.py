"""Immutable global Ethereum observations and historical scan state."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.enums import (
    CollectionScanStatus,
    DeploymentConfidence,
    EvidenceKind,
    EvidenceRetentionStatus,
    FinalityStatus,
    MintClassification,
    MintRoute,
    ScanJobStatus,
    TokenStandard,
)
from app.domain.ids import uuid7
from app.infrastructure.db.base import Base, TimestampMixin
from app.infrastructure.db.models.access import enum_type


class Chain(Base):
    __tablename__ = "chains"
    __table_args__ = (CheckConstraint("chain_id = 1", name="release1_ethereum_mainnet"),)

    chain_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    namespace: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    finality_configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("chain_id", "normalized_address"),
        CheckConstraint(
            "normalized_address = lower(normalized_address)", name="normalized_address"
        ),
        CheckConstraint("length(normalized_address) = 42", name="address_length"),
        CheckConstraint(
            "deployment_confidence_value BETWEEN 0 AND 100", name="deployment_confidence_range"
        ),
        Index("ix_collections_scan_status", "chain_id", "scan_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    chain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chains.chain_id", ondelete="RESTRICT"), nullable=False
    )
    normalized_address: Mapped[str] = mapped_column(String(42), nullable=False)
    checksum_address: Mapped[str] = mapped_column(String(42), nullable=False)
    token_standard: Mapped[TokenStandard] = mapped_column(
        enum_type(TokenStandard, "token_standard"), nullable=False, default=TokenStandard.UNKNOWN
    )
    deployment_block_number: Mapped[int | None] = mapped_column(BigInteger)
    deployment_block_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    deployment_confidence: Mapped[DeploymentConfidence] = mapped_column(
        enum_type(DeploymentConfidence, "deployment_confidence"),
        nullable=False,
        default=DeploymentConfidence.UNKNOWN,
    )
    deployment_confidence_value: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    scan_status: Mapped[CollectionScanStatus] = mapped_column(
        enum_type(CollectionScanStatus, "collection_scan_status"),
        nullable=False,
        default=CollectionScanStatus.PENDING,
    )


class WorkspaceCollection(TimestampMixin, Base):
    __tablename__ = "workspace_collections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "collection_id"),
        Index("ix_workspace_collections_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collections.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(120))
    added_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_users.id", ondelete="RESTRICT"), nullable=False
    )
    notification_settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CollectionImplementation(Base):
    __tablename__ = "collection_implementations"
    __table_args__ = (
        UniqueConstraint("collection_id", "effective_from_block"),
        CheckConstraint(
            "effective_to_block IS NULL OR effective_to_block >= effective_from_block",
            name="implementation_block_interval",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    collection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    implementation_address: Mapped[str] = mapped_column(String(42), nullable=False)
    effective_from_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_to_block: Mapped[int | None] = mapped_column(BigInteger)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ScanJob(TimestampMixin, Base):
    __tablename__ = "scan_jobs"
    __table_args__ = (
        UniqueConstraint("collection_id", "scan_version"),
        CheckConstraint("start_block >= 0 AND end_block >= start_block", name="valid_block_range"),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    collection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collections.id", ondelete="RESTRICT"), nullable=False
    )
    scan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    start_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[ScanJobStatus] = mapped_column(
        enum_type(ScanJobStatus, "scan_job_status"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    error_code: Mapped[str | None] = mapped_column(String(64))


class ScanCheckpoint(Base):
    __tablename__ = "scan_checkpoints"
    __table_args__ = (UniqueConstraint("collection_id", "scan_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    collection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    scan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_committed_block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_committed_block_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChainCursor(Base):
    __tablename__ = "chain_cursors"
    __table_args__ = (UniqueConstraint("chain_id", "purpose"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    chain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chains.chain_id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    last_processed_block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_processed_block_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RawEvidence(Base):
    __tablename__ = "raw_evidence"
    __table_args__ = (
        UniqueConstraint("content_hash"),
        CheckConstraint("octet_length(content_hash) = 32", name="sha256_content_hash"),
        Index("ix_raw_evidence_chain_kind", "chain_id", "kind"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    chain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chains.chain_id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[EvidenceKind] = mapped_column(
        enum_type(EvidenceKind, "evidence_kind"), nullable=False
    )
    content_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    provider_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    transaction_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retention_status: Mapped[EvidenceRetentionStatus] = mapped_column(
        enum_type(EvidenceRetentionStatus, "evidence_retention_status"),
        nullable=False,
        default=EvidenceRetentionStatus.ACTIVE,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MintEvent(Base):
    __tablename__ = "mint_events"
    __table_args__ = (
        UniqueConstraint("chain_id", "transaction_hash", "log_index", "sub_index"),
        CheckConstraint("log_index >= 0 AND sub_index >= 0", name="nonnegative_log_position"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("identity_confidence BETWEEN 0 AND 100", name="identity_confidence_range"),
        Index("ix_mint_events_collection_block", "collection_id", "block_number"),
        Index("ix_mint_events_initiator", "chain_id", "probable_initiator"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    chain_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chains.chain_id", ondelete="RESTRICT"), nullable=False
    )
    collection_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collections.id", ondelete="RESTRICT"), nullable=False
    )
    raw_evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("raw_evidence.id", ondelete="RESTRICT"), nullable=False
    )
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    transaction_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_standard: Mapped[TokenStandard] = mapped_column(
        enum_type(TokenStandard, "mint_event_token_standard"), nullable=False
    )
    token_id: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(78, 0), nullable=False)
    recipient: Mapped[str] = mapped_column(String(42), nullable=False)
    transaction_sender: Mapped[str | None] = mapped_column(String(42))
    operator: Mapped[str | None] = mapped_column(String(42))
    payer: Mapped[str | None] = mapped_column(String(42))
    probable_initiator: Mapped[str | None] = mapped_column(String(42))
    identity_confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    identity_reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    route: Mapped[MintRoute] = mapped_column(
        enum_type(MintRoute, "mint_event_route"), nullable=False, default=MintRoute.UNKNOWN
    )
    classification: Mapped[MintClassification] = mapped_column(
        enum_type(MintClassification, "mint_event_classification"),
        nullable=False,
        default=MintClassification.UNKNOWN_MINT,
    )
    classification_reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    finality: Mapped[FinalityStatus] = mapped_column(
        enum_type(FinalityStatus, "mint_event_finality"), nullable=False
    )
    canonical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
