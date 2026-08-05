"""Signer-only SQLAlchemy metadata and envelope repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    LargeBinary,
    MetaData,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.signer.envelope import KeyEnvelope

SIGNER_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "pk": "pk_%(table_name)s",
}


class SignerBase(DeclarativeBase):
    metadata = MetaData(naming_convention=SIGNER_NAMING_CONVENTION)


class SignerKeyEnvelope(SignerBase):
    __tablename__ = "signer_key_envelopes"
    __table_args__ = (
        UniqueConstraint("environment", "workspace_id", "chain_id", "idempotency_key_hash"),
        CheckConstraint("octet_length(idempotency_key_hash) = 32", name="idempotency_sha256"),
        CheckConstraint("octet_length(nonce) = 12", name="aes_gcm_nonce"),
        CheckConstraint("octet_length(tag) = 16", name="aes_gcm_tag"),
        CheckConstraint("chain_id = 1", name="ethereum_mainnet_only"),
        Index("ix_signer_key_workspace", "environment", "workspace_id", "chain_id"),
    )

    signer_key_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    chain_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    idempotency_key_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_data_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    tag: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    kms_key_arn: Mapped[str] = mapped_column(String(512), nullable=False)
    envelope_version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SignerRequestReplay(SignerBase):
    __tablename__ = "signer_request_replays"
    __table_args__ = (Index("ix_signer_request_replays_expiry", "expires_at"),)

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def to_envelope(model: SignerKeyEnvelope) -> KeyEnvelope:
    return KeyEnvelope(
        signer_key_id=model.signer_key_id,
        environment=model.environment,
        workspace_id=model.workspace_id,
        chain_id=model.chain_id,
        address=model.address,
        ciphertext=model.ciphertext,
        encrypted_data_key=model.encrypted_data_key,
        nonce=model.nonce,
        tag=model.tag,
        kms_key_arn=model.kms_key_arn,
        envelope_version=model.envelope_version,
    )


class SqlAlchemySignerEnvelopeRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def find_by_idempotency(
        self,
        *,
        environment: str,
        workspace_id: UUID,
        chain_id: int,
        idempotency_key_hash: bytes,
    ) -> KeyEnvelope | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(SignerKeyEnvelope).where(
                    SignerKeyEnvelope.environment == environment,
                    SignerKeyEnvelope.workspace_id == workspace_id,
                    SignerKeyEnvelope.chain_id == chain_id,
                    SignerKeyEnvelope.idempotency_key_hash == idempotency_key_hash,
                )
            )
            return to_envelope(model) if model else None

    async def save_or_get(
        self, *, envelope: KeyEnvelope, idempotency_key_hash: bytes
    ) -> tuple[KeyEnvelope, bool]:
        statement = (
            insert(SignerKeyEnvelope)
            .values(
                signer_key_id=envelope.signer_key_id,
                environment=envelope.environment,
                workspace_id=envelope.workspace_id,
                chain_id=envelope.chain_id,
                address=envelope.address,
                idempotency_key_hash=idempotency_key_hash,
                ciphertext=envelope.ciphertext,
                encrypted_data_key=envelope.encrypted_data_key,
                nonce=envelope.nonce,
                tag=envelope.tag,
                kms_key_arn=envelope.kms_key_arn,
                envelope_version=envelope.envelope_version,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    SignerKeyEnvelope.environment,
                    SignerKeyEnvelope.workspace_id,
                    SignerKeyEnvelope.chain_id,
                    SignerKeyEnvelope.idempotency_key_hash,
                ]
            )
            .returning(SignerKeyEnvelope)
        )
        async with self._sessions() as session, session.begin():
            created = (await session.execute(statement)).scalar_one_or_none()
            if created is not None:
                return to_envelope(created), True
            existing = await session.scalar(
                select(SignerKeyEnvelope).where(
                    SignerKeyEnvelope.environment == envelope.environment,
                    SignerKeyEnvelope.workspace_id == envelope.workspace_id,
                    SignerKeyEnvelope.chain_id == envelope.chain_id,
                    SignerKeyEnvelope.idempotency_key_hash == idempotency_key_hash,
                )
            )
            if existing is None:
                raise RuntimeError("signer idempotency conflict was not recoverable")
            return to_envelope(existing), False

    async def find_for_workspace(
        self,
        *,
        signer_key_id: UUID,
        environment: str,
        workspace_id: UUID,
        chain_id: int,
    ) -> KeyEnvelope | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(SignerKeyEnvelope).where(
                    SignerKeyEnvelope.signer_key_id == signer_key_id,
                    SignerKeyEnvelope.environment == environment,
                    SignerKeyEnvelope.workspace_id == workspace_id,
                    SignerKeyEnvelope.chain_id == chain_id,
                )
            )
            return to_envelope(model) if model else None


class SqlAlchemySignerReplayRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def claim(self, *, request_id: UUID, expires_at: datetime) -> bool:
        statement = (
            insert(SignerRequestReplay)
            .values(request_id=request_id, expires_at=expires_at)
            .on_conflict_do_nothing(index_elements=[SignerRequestReplay.request_id])
            .returning(SignerRequestReplay.request_id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.scalar(statement)) is not None
