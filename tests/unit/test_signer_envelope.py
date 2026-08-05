import os
from dataclasses import fields
from uuid import UUID

import pytest
from cryptography.exceptions import InvalidTag

from app.domain.ids import uuid7
from app.signer.envelope import GeneratedDataKey, KeyEnvelope, restore_and_verify_address
from app.signer.service import SignerWalletService


class FakeDataKeyProvider:
    def __init__(self) -> None:
        self.key = os.urandom(32)
        self.contexts: dict[bytes, dict[str, str]] = {}

    async def generate_data_key(self, encryption_context: dict[str, str]) -> GeneratedDataKey:
        encrypted = os.urandom(48)
        self.contexts[encrypted] = encryption_context.copy()
        return GeneratedDataKey(
            plaintext=self.key,
            ciphertext=encrypted,
            key_arn="arn:aws:kms:eu-west-1:000000000000:key/test",
        )

    async def decrypt_data_key(
        self, ciphertext: bytes, encryption_context: dict[str, str]
    ) -> bytes:
        if self.contexts.get(ciphertext) != encryption_context:
            raise PermissionError("encryption context mismatch")
        return self.key


class FakeEnvelopeRepository:
    def __init__(self) -> None:
        self.values: dict[tuple[str, UUID, int, bytes], KeyEnvelope] = {}

    async def find_by_idempotency(self, **values: object) -> KeyEnvelope | None:
        key = (
            str(values["environment"]),
            values["workspace_id"],
            int(values["chain_id"]),
            values["idempotency_key_hash"],
        )
        return self.values.get(key)  # type: ignore[arg-type]

    async def save_or_get(
        self, *, envelope: KeyEnvelope, idempotency_key_hash: bytes
    ) -> tuple[KeyEnvelope, bool]:
        key = (
            envelope.environment,
            envelope.workspace_id,
            envelope.chain_id,
            idempotency_key_hash,
        )
        existing = self.values.get(key)
        if existing is not None:
            return existing, False
        self.values[key] = envelope
        return envelope, True

    async def find_for_workspace(self, **values: object) -> KeyEnvelope | None:
        for envelope in self.values.values():
            if (
                envelope.signer_key_id == values["signer_key_id"]
                and envelope.environment == values["environment"]
                and envelope.workspace_id == values["workspace_id"]
                and envelope.chain_id == values["chain_id"]
            ):
                return envelope
        return None


@pytest.mark.asyncio
async def test_wallet_creation_is_idempotent_and_restorable() -> None:
    repository = FakeEnvelopeRepository()
    provider = FakeDataKeyProvider()
    service = SignerWalletService(repository, provider, environment="test")
    workspace_id = uuid7()

    first = await service.create_wallet(
        workspace_id=workspace_id,
        chain_id=1,
        idempotency_key="request-00000001",
    )
    second = await service.create_wallet(
        workspace_id=workspace_id,
        chain_id=1,
        idempotency_key="request-00000001",
    )

    assert first.created
    assert not second.created
    assert second.signer_key_id == first.signer_key_id
    assert second.address == first.address
    assert len(repository.values) == 1
    assert (
        await service.verify_restore(
            signer_key_id=first.signer_key_id,
            workspace_id=workspace_id,
            chain_id=1,
        )
        == first.address
    )


@pytest.mark.asyncio
async def test_envelope_contains_no_plaintext_and_tampering_fails() -> None:
    repository = FakeEnvelopeRepository()
    provider = FakeDataKeyProvider()
    service = SignerWalletService(repository, provider, environment="test")
    workspace_id = uuid7()
    descriptor = await service.create_wallet(
        workspace_id=workspace_id,
        chain_id=1,
        idempotency_key="request-00000002",
    )
    envelope = next(iter(repository.values.values()))

    assert "private" not in {field.name for field in fields(envelope)}
    assert provider.key not in envelope.ciphertext
    assert provider.key not in envelope.encrypted_data_key

    tampered = KeyEnvelope(
        **{
            **{field.name: getattr(envelope, field.name) for field in fields(envelope)},
            "address": "0x0000000000000000000000000000000000000000",
        }
    )
    with pytest.raises(InvalidTag):
        await restore_and_verify_address(provider=provider, envelope=tampered)
    assert descriptor.address != tampered.address


@pytest.mark.asyncio
async def test_signer_key_lookup_is_bound_to_workspace() -> None:
    repository = FakeEnvelopeRepository()
    service = SignerWalletService(repository, FakeDataKeyProvider(), environment="test")
    owner_workspace = uuid7()
    descriptor = await service.create_wallet(
        workspace_id=owner_workspace,
        chain_id=1,
        idempotency_key="request-00000003",
    )
    with pytest.raises(LookupError, match="not found"):
        await service.verify_restore(
            signer_key_id=descriptor.signer_key_id,
            workspace_id=uuid7(),
            chain_id=1,
        )
