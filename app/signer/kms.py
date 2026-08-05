"""AWS KMS data-key adapter."""

import asyncio
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.signer.envelope import GeneratedDataKey


class KmsOperationError(RuntimeError):
    """Sanitized KMS failure safe for service error boundaries."""


async def kms_call(method: Any, **values: object) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(method, **values)
    except (BotoCoreError, ClientError) as exc:
        if isinstance(exc, ClientError):
            code = str(exc.response.get("Error", {}).get("Code", "ClientError"))
        else:
            code = type(exc).__name__
        raise KmsOperationError(f"AWS KMS operation failed ({code})") from None


class AwsKmsDataKeyProvider:
    def __init__(self, client: Any, *, key_arn: str) -> None:
        self._client = client
        self._key_arn = key_arn

    async def health(self) -> bool:
        response = await kms_call(self._client.describe_key, KeyId=self._key_arn)
        metadata = response.get("KeyMetadata", {})
        return bool(metadata.get("Enabled")) and metadata.get("KeyUsage") == "ENCRYPT_DECRYPT"

    async def generate_data_key(self, encryption_context: dict[str, str]) -> GeneratedDataKey:
        response = await kms_call(
            self._client.generate_data_key,
            KeyId=self._key_arn,
            KeySpec="AES_256",
            EncryptionContext=encryption_context,
        )
        plaintext = bytes(response["Plaintext"])
        ciphertext = bytes(response["CiphertextBlob"])
        key_arn = str(response["KeyId"])
        if not plaintext or not ciphertext or not key_arn:
            raise RuntimeError("AWS KMS returned an incomplete data-key response")
        return GeneratedDataKey(plaintext=plaintext, ciphertext=ciphertext, key_arn=key_arn)

    async def decrypt_data_key(
        self, ciphertext: bytes, encryption_context: dict[str, str]
    ) -> bytes:
        response = await kms_call(
            self._client.decrypt,
            KeyId=self._key_arn,
            CiphertextBlob=ciphertext,
            EncryptionContext=encryption_context,
        )
        plaintext = bytes(response["Plaintext"])
        if len(plaintext) != 32:
            raise RuntimeError("AWS KMS returned an invalid decrypted data key")
        return plaintext
