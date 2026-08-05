"""Telegram dispatcher composition for Release 1 access flows."""

from aiogram import Dispatcher

from app.application.access.challenges import ChallengeService
from app.application.access.ports import SecurityAuditPort
from app.application.access.service import AccessService
from app.application.wallets.service import WalletService
from app.bot.handlers import build_access_router, build_wallet_router
from app.bot.middleware import RequestContextMiddleware, TelegramRateLimitMiddleware
from app.bot.middleware.rate_limit import RateLimiter


def create_dispatcher(
    *,
    access_service: AccessService,
    challenge_service: ChallengeService,
    platform_owner_ids: frozenset[int],
    rate_limiter: RateLimiter,
    security_audit: SecurityAuditPort,
    user_rate_limit_per_minute: int,
    workspace_rate_limit_per_minute: int,
    wallet_service: WalletService,
) -> Dispatcher:
    dispatcher = Dispatcher()
    router = build_access_router()
    wallet_router = build_wallet_router()
    authorization = RequestContextMiddleware(access_service, security_audit)
    rate_limit = TelegramRateLimitMiddleware(
        rate_limiter,
        user_limit_per_minute=user_rate_limit_per_minute,
        workspace_limit_per_minute=workspace_rate_limit_per_minute,
    )
    router.message.middleware(authorization)
    router.message.middleware(rate_limit)
    router.callback_query.middleware(authorization)
    router.callback_query.middleware(rate_limit)
    wallet_router.message.middleware(authorization)
    wallet_router.message.middleware(rate_limit)
    wallet_router.callback_query.middleware(authorization)
    wallet_router.callback_query.middleware(rate_limit)
    dispatcher.include_router(router)
    dispatcher.include_router(wallet_router)
    dispatcher["access_service"] = access_service
    dispatcher["challenge_service"] = challenge_service
    dispatcher["platform_owner_ids"] = platform_owner_ids
    dispatcher["wallet_service"] = wallet_service
    return dispatcher
