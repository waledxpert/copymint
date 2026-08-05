import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app as api_app
from app.infrastructure.config import get_api_settings, get_signer_settings
from app.signer.api import app as signer_app


@pytest.mark.asyncio
async def test_public_health_exposes_release_ceiling() -> None:
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["execution_ceiling"] == "paper"


@pytest.mark.asyncio
async def test_signing_is_release_locked() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=signer_app), base_url="http://signer"
    ) as client:
        response = await client.post("/v1/sign", json={"anything": "is rejected"})
    assert response.status_code == 423
    assert response.json()["detail"]["code"] == "release_locked"


@pytest.mark.asyncio
async def test_services_start_with_test_only_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql://test:test@localhost/copymint_test",
        "QUEUE_URL": "redis://localhost:6379/15",
        "TELEGRAM_BOT_TOKEN": "000000:replace_with_test_token_value",
        "TELEGRAM_WEBHOOK_SECRET": "w" * 32,
        "TELEGRAM_PLATFORM_OWNER_IDS": "[123456789]",
        "SIGNER_INTERNAL_URL": "http://signer:10000",
        "SIGNER_AUTH_SECRET": "s" * 32,
        "SIGNER_DATABASE_URL": "postgresql://signer:test@localhost/copymint_signer_test",
        "AWS_REGION": "eu-west-1",
        "AWS_KMS_KEY_ARN": "arn:aws:kms:eu-west-1:000000000000:key/test",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    get_api_settings.cache_clear()
    get_signer_settings.cache_clear()
    try:
        async with api_app.router.lifespan_context(api_app):
            assert api_app.state.settings.app_env == "test"
        async with signer_app.router.lifespan_context(signer_app):
            assert signer_app.state.settings.app_env == "test"
    finally:
        get_api_settings.cache_clear()
        get_signer_settings.cache_clear()
