"""Idempotent signer-owned wallet creation and restore verification."""

import hashlib
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.ids import uuid7
from app.signer.envelope import (
    DataKeyProvider,
    KeyEnvelope,
    create_key_envelope,
    restore_and_verify_address,
)


@dataclass(frozen=True, slots=True)
class WalletDescriptor:
    signer_key_id: UUID
    workspace_id: UUID
    chain_id: int
    address: str
    created: bool


class SignerEnvelopeRepository(Protocol):
    async def find_by_idempotency(
        self,
        *,
        environment: str,
        workspace_id: UUID,
        chain_id: int,
        idempotency_key_hash: bytes,
    ) -> KeyEnvelope | None: ...

    async def save_or_get(
        self, *, envelope: KeyEnvelope, idempotency_key_hash: bytes
    ) -> tuple[KeyEnvelope, bool]: ...

    async def find_for_workspace(
        self, *, signer_key_id: UUID, environment: str, workspace_id: UUID, chain_id: int
    ) -> KeyEnvelope | None: ...


def hash_idempotency_key(value: str) -> bytes:
    if not 16 <= len(value) <= 128:
        raise ValueError("idempotency key must contain between 16 and 128 characters")
    return hashlib.sha256(value.encode("utf-8")).digest()


class SignerWalletService:
    def __init__(
        self,
        repository: SignerEnvelopeRepository,
        provider: DataKeyProvider,
        *,
        environment: str,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._environment = environment

    async def create_wallet(
        self, *, workspace_id: UUID, chain_id: int, idempotency_key: str
    ) -> WalletDescriptor:
        key_hash = hash_idempotency_key(idempotency_key)
        existing = await self._repository.find_by_idempotency(
            environment=self._environment,
            workspace_id=workspace_id,
            chain_id=chain_id,
            idempotency_key_hash=key_hash,
        )
        if existing is not None:
            return self._descriptor(existing, created=False)

        envelope = await create_key_envelope(
            provider=self._provider,
            environment=self._environment,
            workspace_id=workspace_id,
            chain_id=chain_id,
            signer_key_id=uuid7(),
        )
        persisted, created = await self._repository.save_or_get(
            envelope=envelope, idempotency_key_hash=key_hash
        )
        return self._descriptor(persisted, created=created)

    async def verify_restore(
        self, *, signer_key_id: UUID, workspace_id: UUID, chain_id: int
    ) -> str:
        envelope = await self._repository.find_for_workspace(
            signer_key_id=signer_key_id,
            environment=self._environment,
            workspace_id=workspace_id,
            chain_id=chain_id,
        )
        if envelope is None:
            raise LookupError("signer key was not found")
        return await restore_and_verify_address(provider=self._provider, envelope=envelope)

    @staticmethod
    def _descriptor(envelope: KeyEnvelope, *, created: bool) -> WalletDescriptor:
        return WalletDescriptor(
            signer_key_id=envelope.signer_key_id,
            workspace_id=envelope.workspace_id,
            chain_id=envelope.chain_id,
            address=envelope.address,
            created=created,
        )
