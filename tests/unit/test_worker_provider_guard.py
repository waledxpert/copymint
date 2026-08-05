from typing import Any

import pytest
from pydantic import SecretStr

from app.infrastructure.config import WorkerSettings
from app.workers import provider_guard


def settings() -> WorkerSettings:
    return WorkerSettings(
        app_env="test",
        database_url=SecretStr("postgresql://example.invalid/db"),
        queue_url=SecretStr("redis://example.invalid/0"),
        chainstack_ethereum_http_url=SecretStr("https://example.invalid/rpc"),
        chainstack_ethereum_wss_url=SecretStr("wss://example.invalid/ws"),
    )


def test_worker_provider_guard_propagates_startup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(runtime_settings: WorkerSettings) -> None:
        raise RuntimeError("wrong chain")

    monkeypatch.setattr(provider_guard, "verify_provider", fail)
    with pytest.raises(RuntimeError, match="wrong chain"):
        provider_guard.run_provider_guard(settings())


def test_worker_provider_guard_completes_successfully(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    async def pass_check(runtime_settings: WorkerSettings) -> None:
        calls.append(runtime_settings.ethereum_chain_id)

    monkeypatch.setattr(provider_guard, "verify_provider", pass_check)
    provider_guard.run_provider_guard(settings())
    assert calls == [1]
