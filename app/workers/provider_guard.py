"""Fail worker startup when its Ethereum provider is misconfigured."""

import asyncio
import platform
from typing import Any

from celery.signals import worker_init

from app.application.ethereum.collections import EthereumCollectionDiscovery
from app.infrastructure.config import WorkerSettings, get_worker_settings
from app.infrastructure.ethereum import JsonRpcEvmProvider


async def verify_provider(settings: WorkerSettings) -> None:
    provider = JsonRpcEvmProvider(endpoint=settings.chainstack_ethereum_http_url.get_secret_value())
    await EthereumCollectionDiscovery(provider, chain_id=settings.ethereum_chain_id).verify_chain()
    await provider.block("finalized")


def run_provider_guard(settings: WorkerSettings | None = None) -> None:
    runtime_settings = settings or get_worker_settings()
    if platform.system() == "Windows":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(verify_provider(runtime_settings))
        return
    asyncio.run(verify_provider(runtime_settings))


@worker_init.connect  # type: ignore[untyped-decorator]
def verify_provider_at_worker_start(**kwargs: Any) -> None:
    run_provider_guard()
