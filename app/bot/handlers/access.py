"""Invite request, status, owner decision, and revocation interactions."""

from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.access.challenges import ChallengeService, InvalidChallenge
from app.application.access.context import (
    AccessError,
    RequestContext,
    TelegramIdentity,
)
from app.application.access.service import AccessService
from app.domain.enums import ChallengeAction
from app.domain.ids import uuid7

CALLBACK_PREFIX = "access:v1"


def callback_data(action: str, token: str) -> str:
    value = f"{CALLBACK_PREFIX}:{action}:{token}"
    if len(value.encode("utf-8")) > 64:
        raise ValueError("Telegram callback data exceeds 64 bytes")
    return value


def require_identity(identity: TelegramIdentity | None) -> TelegramIdentity:
    if identity is None:
        raise AccessError("Telegram identity is unavailable for this update.")
    return identity


def require_context(context: RequestContext | None, error: AccessError | None) -> RequestContext:
    if context is not None:
        return context
    if error is not None:
        raise error
    raise AccessError("Authorization context is unavailable.")


async def owner_keyboard(
    *,
    request_id: UUID,
    owner_id: int,
    challenge_service: ChallengeService,
) -> InlineKeyboardMarkup:
    owner = RequestContext.platform_owner(
        TelegramIdentity(
            telegram_user_id=owner_id,
            chat_id=owner_id,
            chat_type="private",
        )
    )
    approve = await challenge_service.issue(
        owner,
        action=ChallengeAction.APPROVE_ACCESS,
        resource_type="access_request",
        resource_id=request_id,
    )
    reject = await challenge_service.issue(
        owner,
        action=ChallengeAction.REJECT_ACCESS,
        resource_type="access_request",
        resource_id=request_id,
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Approve",
                    callback_data=callback_data("approve", approve.token),
                ),
                InlineKeyboardButton(
                    text="Reject",
                    callback_data=callback_data("reject", reject.token),
                ),
            ]
        ]
    )


def build_access_router() -> Router:
    router = Router(name="access")

    @router.message(CommandStart())
    async def start(
        message: Message,
        bot: Bot,
        telegram_identity: TelegramIdentity | None,
        access_service: AccessService,
        challenge_service: ChallengeService,
        platform_owner_ids: frozenset[int],
    ) -> None:
        try:
            identity = require_identity(telegram_identity)
            outcome = await access_service.request_access(identity)
        except AccessError as exc:
            await message.answer(str(exc))
            return

        if outcome.state == "active":
            await message.answer("Your CopyMint access is active. Use /help to see commands.")
            return
        if outcome.state == "cooldown":
            await message.answer("Your previous request was rejected. Please try again later.")
            return

        await message.answer("Access request received. You will be notified after owner review.")
        if not outcome.created or outcome.request_id is None:
            return

        for owner_id in platform_owner_ids:
            keyboard = await owner_keyboard(
                request_id=outcome.request_id,
                owner_id=owner_id,
                challenge_service=challenge_service,
            )
            await bot.send_message(
                owner_id,
                "\n".join(
                    (
                        "COPYMINT ACCESS REQUEST",
                        f"Request: {outcome.request_id}",
                        f"Telegram ID: {identity.telegram_user_id}",
                        f"Username: @{identity.username}"
                        if identity.username
                        else "Username: none",
                        f"Name: {identity.display_name or 'not provided'}",
                    )
                ),
                reply_markup=keyboard,
            )

    @router.message(Command("access_status"))
    async def access_status(
        message: Message,
        telegram_identity: TelegramIdentity | None,
        access_service: AccessService,
    ) -> None:
        try:
            outcome = await access_service.access_status(require_identity(telegram_identity))
        except AccessError as exc:
            await message.answer(str(exc))
            return
        await message.answer(f"CopyMint access status: {outcome.state}.")

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "CopyMint Release 1 commands:\n"
            "/access_status — view approval status\n"
            "/status — system status\n\n"
            "Collection, analytics, wallet, and paper commands unlock in later phases."
        )

    @router.message(Command("admin_requests"))
    async def admin_requests(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        access_service: AccessService,
        challenge_service: ChallengeService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            pending = await access_service.pending_requests(context)
        except AccessError as exc:
            await message.answer(str(exc))
            return
        if not pending:
            await message.answer("There are no pending access requests.")
            return
        for request in pending:
            keyboard = await owner_keyboard(
                request_id=request.id,
                owner_id=context.telegram_user_id,
                challenge_service=challenge_service,
            )
            await message.answer(
                f"Request {request.id}\nTelegram ID: {request.telegram_user_id}",
                reply_markup=keyboard,
            )

    @router.message(Command("admin_revoke"))
    async def admin_revoke(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        challenge_service: ChallengeService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            context.require_platform_owner()
            parts = (message.text or "").split(maxsplit=1)
            if len(parts) != 2 or not parts[1].isdigit():
                await message.answer("Usage: /admin_revoke <numeric_telegram_user_id>")
                return
            target_id = int(parts[1])
            challenge = await challenge_service.issue(
                context,
                action=ChallengeAction.REVOKE_ACCESS,
                resource_type="platform_user",
                resource_id=uuid7(),
                authoritative_payload={"target_telegram_user_id": target_id},
            )
        except AccessError as exc:
            await message.answer(str(exc))
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Confirm revocation",
                        callback_data=callback_data("revoke", challenge.token),
                    )
                ]
            ]
        )
        await message.answer(
            f"Revoke CopyMint access for Telegram ID {target_id}?",
            reply_markup=keyboard,
        )

    @router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}:"))
    async def access_callback(
        callback: CallbackQuery,
        bot: Bot,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        access_service: AccessService,
        challenge_service: ChallengeService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            parts = (callback.data or "").split(":", maxsplit=3)
            if len(parts) != 4:
                raise InvalidChallenge("Malformed confirmation.")
            action_name, token = parts[2], parts[3]
            actions = {
                "approve": ChallengeAction.APPROVE_ACCESS,
                "reject": ChallengeAction.REJECT_ACCESS,
                "revoke": ChallengeAction.REVOKE_ACCESS,
            }
            action = actions.get(action_name)
            if action is None:
                raise InvalidChallenge("Unknown confirmation action.")
            challenge = await challenge_service.consume(
                context,
                token=token,
                expected_action=action,
            )

            if action is ChallengeAction.APPROVE_ACCESS:
                result = await access_service.approve(context, challenge.resource_id)
                response = f"Approved Telegram ID {result.telegram_user_id}."
                notification_target = result.telegram_user_id
                target_message = "Your CopyMint access request was approved. Use /help to begin."
            elif action is ChallengeAction.REJECT_ACCESS:
                result = await access_service.reject(context, challenge.resource_id)
                response = f"Rejected Telegram ID {result.telegram_user_id}."
                notification_target = result.telegram_user_id
                target_message = "Your CopyMint access request was not approved."
            else:
                target = challenge.authoritative_payload.get("target_telegram_user_id")
                if not isinstance(target, int):
                    raise InvalidChallenge("Revocation target is invalid.")
                await access_service.revoke(context, target)
                response = f"Revoked Telegram ID {target}."
                notification_target = target
                target_message = "Your CopyMint access has been revoked."
        except AccessError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        await callback.answer(response, show_alert=True)
        await bot.send_message(notification_target, target_message)
        if callback.message is not None:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=response,
            )

    return router
