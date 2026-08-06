"""Telegram command and callback handlers."""

from app.bot.handlers.access import build_access_router
from app.bot.handlers.collections import build_collection_router
from app.bot.handlers.wallets import build_wallet_router

__all__ = ["build_access_router", "build_collection_router", "build_wallet_router"]
