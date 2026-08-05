"""Resolve Telegram events into server-derived request context."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.application.access.context import AccessError, TelegramIdentity
from app.application.access.ports import SecurityAuditPort
from app.application.access.service import AccessService
from app.domain.ids import uuid7

logger = logging.getLogger(__name__)
PUBLIC_COMMANDS = ("/start", "/access_status", "/help")


def identity_from_event(event: TelegramObject) -> TelegramIdentity | None:
    if isinstance(event, Message):
        if event.from_user is None:
            return None
        user = event.from_user
        chat = event.chat
    elif isinstance(event, CallbackQuery):
        if event.message is None:
            return None
        user = event.from_user
        chat = event.message.chat
    else:
        return None

    display_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return TelegramIdentity(
        telegram_user_id=user.id,
        chat_id=chat.id,
        chat_type=chat.type,
        username=user.username,
        display_name=display_name or None,
    )


class RequestContextMiddleware(BaseMiddleware):
    """Attach identity, optional context, and a safe authorization error to handler data."""

    def __init__(
        self,
        access_service: AccessService,
        security_audit: SecurityAuditPort | None = None,
    ) -> None:
        self._access_service = access_service
        self._security_audit = security_audit

    @staticmethod
    def _is_public_message(event: TelegramObject) -> bool:
        return isinstance(event, Message) and (event.text or "").startswith(PUBLIC_COMMANDS)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity = identity_from_event(event)
        data["telegram_identity"] = identity
        data["request_context"] = None
        data["access_error"] = None
        if identity is not None:
            try:
                data["request_context"] = await self._access_service.resolve_context(identity)
            except AccessError as exc:
                data["access_error"] = exc
                if self._security_audit is not None and not self._is_public_message(event):
                    correlation_id = uuid7()
                    await self._security_audit.unauthorized_attempt(
                        identity=identity,
                        action=type(event).__name__,
                        code=exc.code,
                        correlation_id=correlation_id,
                    )
                    logger.warning(
                        "Unauthorized Telegram action",
                        extra={
                            "event": "unauthorized_telegram_action",
                            "correlation_id": correlation_id,
                        },
                    )
        return await handler(event, data)
