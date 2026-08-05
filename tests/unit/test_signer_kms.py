import pytest
from botocore.exceptions import ClientError

from app.signer.kms import AwsKmsDataKeyProvider, KmsOperationError


class FakeKmsClient:
    def generate_data_key(self, **values: object) -> dict[str, object]:
        assert values["KeySpec"] == "AES_256"
        assert values["EncryptionContext"] == {"purpose": "test"}
        return {
            "Plaintext": b"p" * 32,
            "CiphertextBlob": b"encrypted-data-key",
            "KeyId": values["KeyId"],
        }

    def decrypt(self, **values: object) -> dict[str, object]:
        assert values["CiphertextBlob"] == b"encrypted-data-key"
        return {"Plaintext": b"p" * 32}

    def describe_key(self, **values: object) -> dict[str, object]:
        return {"KeyMetadata": {"Enabled": True, "KeyUsage": "ENCRYPT_DECRYPT"}}


@pytest.mark.asyncio
async def test_aws_kms_adapter_requests_and_validates_aes_256_data_keys() -> None:
    provider = AwsKmsDataKeyProvider(FakeKmsClient(), key_arn="arn:test")
    generated = await provider.generate_data_key({"purpose": "test"})
    assert generated.plaintext == b"p" * 32
    assert generated.ciphertext == b"encrypted-data-key"
    assert await provider.decrypt_data_key(generated.ciphertext, {"purpose": "test"}) == b"p" * 32
    assert await provider.health()


@pytest.mark.asyncio
async def test_aws_kms_adapter_sanitizes_provider_errors() -> None:
    class DeniedClient:
        def describe_key(self, **values: object) -> None:
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "account-and-key-identifiers-must-not-escape",
                    }
                },
                "DescribeKey",
            )

    provider = AwsKmsDataKeyProvider(DeniedClient(), key_arn="sensitive-key-identifier")
    with pytest.raises(KmsOperationError) as captured:
        await provider.health()
    assert str(captured.value) == "AWS KMS operation failed (AccessDeniedException)"
    assert captured.value.__cause__ is None
