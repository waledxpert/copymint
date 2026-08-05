"""Strict, process-specific environment settings with safe diagnostics."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """Non-secret settings required by every process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    release_execution_ceiling: Literal["paper"] = "paper"

    def safe_runtime_context(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "release_execution_ceiling": self.release_execution_ceiling,
        }


class DatabaseSettings(RuntimeSettings):
    """Minimum settings for migrations and application repositories."""

    database_url: SecretStr


class ApiSettings(DatabaseSettings):
    """Public bot/API settings. Contains no Chainstack or KMS credentials."""

    queue_url: SecretStr
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr
    telegram_platform_owner_ids: list[int]
    signer_internal_url: str
    signer_auth_secret: SecretStr
    ethereum_chain_id: Literal[1] = 1
    max_execution_wallets_per_workspace: int = Field(default=1, ge=1, le=100)
    telegram_user_rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    workspace_rate_limit_per_minute: int = Field(default=120, ge=1, le=5000)

    @field_validator("telegram_platform_owner_ids")
    @classmethod
    def owner_ids_must_be_present(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("at least one numeric Telegram platform owner ID is required")
        if any(owner_id <= 0 for owner_id in value):
            raise ValueError("Telegram platform owner IDs must be positive integers")
        return sorted(set(value))

    @field_validator("telegram_webhook_secret", "signer_auth_secret")
    @classmethod
    def control_secrets_must_be_long(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("control secrets must contain at least 32 characters")
        return value

    def safe_runtime_context(self) -> dict[str, object]:
        return {
            **super().safe_runtime_context(),
            "ethereum_chain_id": self.ethereum_chain_id,
            "max_execution_wallets_per_workspace": self.max_execution_wallets_per_workspace,
            "telegram_user_rate_limit_per_minute": self.telegram_user_rate_limit_per_minute,
            "workspace_rate_limit_per_minute": self.workspace_rate_limit_per_minute,
        }


class WorkerSettings(DatabaseSettings):
    """Blockchain worker settings. Contains no Telegram, signer, or KMS credentials."""

    queue_url: SecretStr
    chainstack_ethereum_http_url: SecretStr
    chainstack_ethereum_wss_url: SecretStr
    ethereum_chain_id: Literal[1] = 1
    ethereum_reorg_lookback: int = Field(default=64, ge=1, le=2048)
    indexer_initial_chunk: int = Field(default=2000, ge=1, le=5000)
    indexer_max_chunk: int = Field(default=5000, ge=1, le=5000)

    @model_validator(mode="after")
    def chunk_bounds_are_ordered(self) -> Self:
        if self.indexer_initial_chunk > self.indexer_max_chunk:
            raise ValueError("INDEXER_INITIAL_CHUNK cannot exceed INDEXER_MAX_CHUNK")
        return self

    def safe_runtime_context(self) -> dict[str, object]:
        return {
            **super().safe_runtime_context(),
            "ethereum_chain_id": self.ethereum_chain_id,
            "ethereum_reorg_lookback": self.ethereum_reorg_lookback,
            "indexer_initial_chunk": self.indexer_initial_chunk,
            "indexer_max_chunk": self.indexer_max_chunk,
        }


class SignerSettings(RuntimeSettings):
    """Private signer settings. Contains no Telegram, queue, or Chainstack credentials."""

    signer_database_url: SecretStr
    signer_auth_secret: SecretStr
    aws_region: str
    aws_kms_key_arn: SecretStr
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None

    @field_validator("signer_auth_secret")
    @classmethod
    def signer_secret_must_be_long(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SIGNER_AUTH_SECRET must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def static_aws_credentials_are_complete(self) -> Self:
        if (self.aws_access_key_id is None) != (self.aws_secret_access_key is None):
            raise ValueError(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be supplied together"
            )
        return self

    def aws_client_credentials(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if self.aws_access_key_id is not None and self.aws_secret_access_key is not None:
            values["aws_access_key_id"] = self.aws_access_key_id.get_secret_value()
            values["aws_secret_access_key"] = self.aws_secret_access_key.get_secret_value()
        if self.aws_session_token is not None:
            values["aws_session_token"] = self.aws_session_token.get_secret_value()
        return values


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    return ApiSettings()


@lru_cache(maxsize=1)
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()


@lru_cache(maxsize=1)
def get_signer_settings() -> SignerSettings:
    return SignerSettings()


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()
