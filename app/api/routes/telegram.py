"""Authenticated, idempotent Telegram webhook boundary."""

import logging
import secrets
from typing import Protocol

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.application.access.updates import TelegramUpdateDeduplicator
from app.domain.ids import uuid7

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


class TelegramRuntime(Protocol):
    bot: Bot
    dispatcher: Dispatcher
    updates: TelegramUpdateDeduplicator
    webhook_secret: str
    bot_id: str


def runtime_from(request: Request) -> TelegramRuntime:
    runtime: TelegramRuntime | None = getattr(request.app.state, "telegram_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "telegram_runtime_unavailable"},
        )
    return runtime


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    runtime = runtime_from(request)
    supplied_secret = x_telegram_bot_api_secret_token or ""
    if not secrets.compare_digest(supplied_secret, runtime.webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_webhook_secret"},
        )

    try:
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": runtime.bot})
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_telegram_update"},
        ) from exc

    correlation_id = uuid7()
    claimed = await runtime.updates.claim(
        bot_id=runtime.bot_id,
        update_id=update.update_id,
        correlation_id=correlation_id,
    )
    if not claimed:
        return {"status": "duplicate"}

    try:
        await runtime.dispatcher.feed_update(runtime.bot, update)
    except Exception:
        await runtime.updates.failed(
            bot_id=runtime.bot_id,
            update_id=update.update_id,
            failure_code="dispatch_failed",
        )
        logger.exception(
            "Telegram update dispatch failed",
            extra={"event": "telegram_dispatch_failed", "correlation_id": correlation_id},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "telegram_dispatch_failed"},
        ) from None

    await runtime.updates.processed(bot_id=runtime.bot_id, update_id=update.update_id)
    return {"status": "processed"}
