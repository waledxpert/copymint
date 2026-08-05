"""AWS KMS envelope encryption for signer-owned Ethereum keys."""

import json
import os
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from eth_account import Account

ENVELOPE_VERSION = 1
GCM_NONCE_BYTES = 12
GCM_TAG_BYTES = 16


@dataclass(frozen=True, slots=True)
class GeneratedDataKey:
    plaintext: bytes
    ciphertext: bytes
    key_arn: str


class DataKeyProvider(Protocol):
    async def generate_data_key(self, encryption_context: dict[str, str]) -> GeneratedDataKey: ...

    async def decrypt_data_key(
        self, ciphertext: bytes, encryption_context: dict[str, str]
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class KeyEnvelope:
    signer_key_id: UUID
    environment: str
    workspace_id: UUID
    chain_id: int
    address: str
    ciphertext: bytes
    encrypted_data_key: bytes
    nonce: bytes
    tag: bytes
    kms_key_arn: str
    envelope_version: int = ENVELOPE_VERSION

    def encryption_context(self) -> dict[str, str]:
        return encryption_context(
            environment=self.environment,
            workspace_id=self.workspace_id,
            chain_id=self.chain_id,
            signer_key_id=self.signer_key_id,
        )


def encryption_context(
    *, environment: str, workspace_id: UUID, chain_id: int, signer_key_id: UUID
) -> dict[str, str]:
    return {
        "environment": environment,
        "workspace_id": str(workspace_id),
        "chain_id": str(chain_id),
        "signer_key_id": str(signer_key_id),
        "purpose": "copymint-execution-wallet",
    }


def authenticated_data(context: dict[str, str], address: str) -> bytes:
    values = {"envelope_version": ENVELOPE_VERSION, "address": address, **context}
    return json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")


def zeroize(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


async def create_key_envelope(
    *,
    provider: DataKeyProvider,
    environment: str,
    workspace_id: UUID,
    chain_id: int,
    signer_key_id: UUID,
) -> KeyEnvelope:
    if chain_id != 1:
        raise ValueError("Release 1 wallet creation supports Ethereum mainnet only")
    context = encryption_context(
        environment=environment,
        workspace_id=workspace_id,
        chain_id=chain_id,
        signer_key_id=signer_key_id,
    )
    private_key = ec.generate_private_key(ec.SECP256K1())
    private_buffer = bytearray(private_key.private_numbers().private_value.to_bytes(32, "big"))
    data_buffer = bytearray()
    try:
        address = Account.from_key(bytes(private_buffer)).address
        data_key = await provider.generate_data_key(context)
        if len(data_key.plaintext) != 32:
            raise ValueError("KMS returned an invalid AES-256 data key")
        data_buffer.extend(data_key.plaintext)
        nonce = os.urandom(GCM_NONCE_BYTES)
        encrypted = AESGCM(bytes(data_buffer)).encrypt(
            nonce,
            bytes(private_buffer),
            authenticated_data(context, address),
        )
        return KeyEnvelope(
            signer_key_id=signer_key_id,
            environment=environment,
            workspace_id=workspace_id,
            chain_id=chain_id,
            address=address,
            ciphertext=encrypted[:-GCM_TAG_BYTES],
            encrypted_data_key=data_key.ciphertext,
            nonce=nonce,
            tag=encrypted[-GCM_TAG_BYTES:],
            kms_key_arn=data_key.key_arn,
        )
    finally:
        zeroize(private_buffer)
        zeroize(data_buffer)


async def restore_and_verify_address(*, provider: DataKeyProvider, envelope: KeyEnvelope) -> str:
    context = envelope.encryption_context()
    data_buffer = bytearray(await provider.decrypt_data_key(envelope.encrypted_data_key, context))
    private_buffer = bytearray()
    try:
        if len(data_buffer) != 32:
            raise ValueError("KMS returned an invalid AES-256 data key")
        private_buffer.extend(
            AESGCM(bytes(data_buffer)).decrypt(
                envelope.nonce,
                envelope.ciphertext + envelope.tag,
                authenticated_data(context, envelope.address),
            )
        )
        restored = cast(str, Account.from_key(bytes(private_buffer)).address)
        if restored != envelope.address:
            raise ValueError("restored private key does not match the stored address")
        return restored
    finally:
        zeroize(private_buffer)
        zeroize(data_buffer)
