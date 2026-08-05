import pytest
from pydantic import ValidationError

from app.infrastructure.config.settings import ApiSettings, SignerSettings, WorkerSettings


def api_values() -> dict[str, object]:
    return {
        "app_env": "local",
        "database_url": "postgresql://user:password@localhost/copymint",
        "queue_url": "redis://localhost:6379/0",
        "telegram_bot_token": "000000000:replace_with_test_token_value",
        "telegram_webhook_secret": "w" * 32,
        "telegram_platform_owner_ids": [22, 11, 22],
        "signer_internal_url": "http://signer:10000",
        "signer_auth_secret": "s" * 32,
    }


def worker_values() -> dict[str, object]:
    return {
        "database_url": "postgresql://user:password@localhost/copymint",
        "queue_url": "redis://localhost:6379/0",
        "chainstack_ethereum_http_url": "https://example.invalid/http-secret",
        "chainstack_ethereum_wss_url": "wss://example.invalid/ws-secret",
    }


def test_api_settings_deduplicate_owner_ids_and_hide_secrets() -> None:
    settings = ApiSettings(**api_values())
    assert settings.telegram_platform_owner_ids == [11, 22]
    assert "password" not in repr(settings.database_url)
    assert settings.safe_runtime_context() == {
        "app_env": "local",
        "log_level": "INFO",
        "release_execution_ceiling": "paper",
        "ethereum_chain_id": 1,
        "max_execution_wallets_per_workspace": 1,
        "telegram_user_rate_limit_per_minute": 30,
        "workspace_rate_limit_per_minute": 120,
    }


def test_api_settings_require_an_owner() -> None:
    values = api_values()
    values["telegram_platform_owner_ids"] = []
    with pytest.raises(ValidationError, match="at least one numeric"):
        ApiSettings(**values)


def test_release_ceiling_cannot_be_raised_by_environment() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(**api_values(), release_execution_ceiling="manual")


def test_worker_chunk_bounds_fail_closed() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        WorkerSettings(**worker_values(), indexer_initial_chunk=5000, indexer_max_chunk=1000)


def test_process_settings_enforce_least_privilege_fields() -> None:
    assert "telegram_bot_token" not in WorkerSettings.model_fields
    assert "chainstack_ethereum_http_url" not in ApiSettings.model_fields
    assert "telegram_bot_token" not in SignerSettings.model_fields
    assert "chainstack_ethereum_http_url" not in SignerSettings.model_fields


def test_signer_secret_must_be_long() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        SignerSettings(
            signer_database_url="postgresql://signer:password@localhost/copymint",
            signer_auth_secret="short",
            aws_region="eu-west-1",
            aws_kms_key_arn="arn:aws:kms:eu-west-1:000000000000:key/example",
        )
