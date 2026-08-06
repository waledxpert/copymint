"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.api.routes.health import router as health_router
from app.api.routes.telegram import router as telegram_router
from app.application.access.challenges import ChallengeService
from app.application.access.service import AccessService
from app.application.access.updates import TelegramUpdateDeduplicator
from app.application.ethereum.collection_service import CollectionService
from app.application.wallets.service import WalletService
from app.bot.factory import create_dispatcher
from app.infrastructure.collection_scan_queue import CeleryCollectionScanQueue
from app.infrastructure.config import get_api_settings
from app.infrastructure.db.repositories import (
    SqlAlchemyAccessRepository,
    SqlAlchemyChallengeRepository,
    SqlAlchemySecurityAudit,
    SqlAlchemyTelegramUpdateRepository,
    SqlAlchemyWalletRepository,
    SqlAlchemyWorkspaceCollectionRepository,
)
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.observability import configure_logging
from app.infrastructure.queue import RedisRateLimiter
from app.infrastructure.signer_client import HttpSignerWalletClient
from app.infrastructure.wallet_balance_queue import CeleryWalletBalanceRefreshQueue


@dataclass(slots=True)
class ApiRuntime:
    bot: Bot
    dispatcher: Dispatcher
    updates: TelegramUpdateDeduplicator
    webhook_secret: str
    bot_id: str
    engine: AsyncEngine
    redis: Redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_api_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    owner_ids = frozenset(settings.telegram_platform_owner_ids)
    access_service = AccessService(
        SqlAlchemyAccessRepository(sessions), platform_owner_ids=owner_ids
    )
    challenge_service = ChallengeService(SqlAlchemyChallengeRepository(sessions))
    wallet_service = WalletService(
        SqlAlchemyWalletRepository(sessions),
        HttpSignerWalletClient(
            base_url=settings.signer_internal_url,
            auth_secret=settings.signer_auth_secret.get_secret_value(),
        ),
        max_wallets_per_workspace=settings.max_execution_wallets_per_workspace,
        chain_id=settings.ethereum_chain_id,
        balance_refresh=CeleryWalletBalanceRefreshQueue(
            broker_url=settings.queue_url.get_secret_value()
        ),
    )
    collection_service = CollectionService(
        SqlAlchemyWorkspaceCollectionRepository(sessions),
        CeleryCollectionScanQueue(broker_url=settings.queue_url.get_secret_value()),
    )
    redis = Redis.from_url(settings.queue_url.get_secret_value())
    rate_limiter = RedisRateLimiter(redis, environment=settings.app_env)
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    app.state.telegram_runtime = ApiRuntime(
        bot=bot,
        dispatcher=create_dispatcher(
            access_service=access_service,
            challenge_service=challenge_service,
            platform_owner_ids=owner_ids,
            rate_limiter=rate_limiter,
            security_audit=SqlAlchemySecurityAudit(sessions),
            user_rate_limit_per_minute=settings.telegram_user_rate_limit_per_minute,
            workspace_rate_limit_per_minute=settings.workspace_rate_limit_per_minute,
            wallet_service=wallet_service,
            collection_service=collection_service,
        ),
        updates=TelegramUpdateDeduplicator(SqlAlchemyTelegramUpdateRepository(sessions)),
        webhook_secret=settings.telegram_webhook_secret.get_secret_value(),
        bot_id=str(bot.id),
        engine=engine,
        redis=redis,
    )
    try:
        yield
    finally:
        await bot.session.close()
        await redis.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title="CopyMint API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(telegram_router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=10000)  # noqa: S104


if __name__ == "__main__":
    run()
