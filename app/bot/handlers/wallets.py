"""Workspace-private execution-wallet Telegram interactions."""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.application.access.challenges import ChallengeService
from app.application.access.context import AccessError, RequestContext
from app.application.wallets.service import WalletService
from app.bot.handlers.access import callback_data as bounded_callback_data
from app.bot.handlers.access import require_context
from app.domain.enums import ChallengeAction
from app.domain.ids import uuid7

CALLBACK_PREFIX = "wallet:v1"
CUSTODY_NOTICE = (
    "CopyMint will create a custodial Ethereum wallet. Its private key is encrypted inside "
    "the isolated signer and will never be sent through Telegram. Do not fund this wallet "
    "until the production custody and recovery policy is approved. Release 1 cannot sign or "
    "broadcast transactions."
)


def wallet_callback_data(token: str) -> str:
    value = f"{CALLBACK_PREFIX}:create:{token}"
    # Reuse the Telegram byte-length guard while preserving this router's prefix.
    bounded_callback_data("create", token)
    if len(value.encode("utf-8")) > 64:
        raise ValueError("Telegram callback data exceeds 64 bytes")
    return value


def format_wei(value: int) -> str:
    whole, remainder = divmod(value, 10**18)
    if remainder == 0:
        return str(whole)
    return f"{whole}.{remainder:018d}".rstrip("0")


def build_wallet_router() -> Router:
    router = Router(name="wallets")

    @router.message(Command("create_wallet"))
    async def create_wallet_command(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        challenge_service: ChallengeService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            workspace_id = context.require_workspace()
            idempotency_key = f"wallet-{uuid7()}"
            challenge = await challenge_service.issue(
                context,
                action=ChallengeAction.CREATE_WALLET,
                resource_type="workspace",
                resource_id=workspace_id,
                authoritative_payload={"idempotency_key": idempotency_key, "chain_id": 1},
            )
        except AccessError as exc:
            await message.answer(str(exc))
            return
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="I understand — create wallet",
                        callback_data=wallet_callback_data(challenge.token),
                    )
                ]
            ]
        )
        await message.answer(CUSTODY_NOTICE, reply_markup=keyboard)

    @router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}:create:"))
    async def create_wallet_callback(
        callback: CallbackQuery,
        bot: Bot,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        challenge_service: ChallengeService,
        wallet_service: WalletService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            token = (callback.data or "").removeprefix(f"{CALLBACK_PREFIX}:create:")
            challenge = await challenge_service.consume(
                context, token=token, expected_action=ChallengeAction.CREATE_WALLET
            )
            if challenge.resource_id != context.require_workspace():
                raise AccessError("Wallet confirmation does not belong to this workspace.")
            idempotency_key = challenge.authoritative_payload.get("idempotency_key")
            if not isinstance(idempotency_key, str):
                raise AccessError("Wallet confirmation payload is invalid.")
            wallet, created = await wallet_service.create_wallet(
                context, idempotency_key=idempotency_key
            )
        except AccessError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        state = "created" if created else "already created"
        await callback.answer(f"Execution wallet {state}.", show_alert=True)
        if callback.message is not None:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=(
                    f"Ethereum execution wallet {state}:\n{wallet.address}\n\n"
                    "Signing and broadcasting remain disabled in Release 1."
                ),
            )

    @router.message(Command("wallets"))
    async def list_wallets_command(
        message: Message,
        request_context: RequestContext | None,
        access_error: AccessError | None,
        wallet_service: WalletService,
    ) -> None:
        try:
            context = require_context(request_context, access_error)
            wallets = await wallet_service.list_wallets(context)
        except AccessError as exc:
            await message.answer(str(exc))
            return
        if not wallets:
            await message.answer("No execution wallet exists. Use /create_wallet to create one.")
            return
        lines = ["Your Ethereum execution wallets:"]
        for index, wallet in enumerate(wallets, start=1):
            lines.append(
                f"{index}. {wallet.address}\n"
                f"   Balance snapshot: {format_wei(wallet.balance_wei)} ETH"
            )
        lines.append("Balance refresh queued. Reopen /wallets shortly for the latest snapshot.")
        lines.append("Signing and broadcasting are disabled in Release 1.")
        await message.answer("\n".join(lines))

    return router
