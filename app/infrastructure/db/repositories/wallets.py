"""PostgreSQL execution-wallet repository with workspace RLS context."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.wallets.ports import SignerWalletResult, WalletRecord
from app.domain.enums import ActorType, Severity, WalletStatus
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import AuditLog, ExecutionWallet
from app.infrastructure.db.repositories.access import set_workspace_context


def wallet_record(model: ExecutionWallet) -> WalletRecord:
    return WalletRecord(
        id=model.id,
        workspace_id=model.workspace_id,
        chain_id=model.chain_id,
        address=model.address,
        signer_key_id=model.signer_key_id,
        status=model.status,
        balance_wei=int(model.balance_wei),
        balance_block_number=model.balance_block_number,
        balance_refreshed_at=model.balance_refreshed_at,
    )


class SqlAlchemyWalletRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def find_by_idempotency(
        self, *, workspace_id: UUID, idempotency_key_hash: bytes
    ) -> WalletRecord | None:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            model = await session.scalar(
                select(ExecutionWallet).where(
                    ExecutionWallet.workspace_id == workspace_id,
                    ExecutionWallet.idempotency_key_hash == idempotency_key_hash,
                )
            )
            return wallet_record(model) if model else None

    async def count_active(self, *, workspace_id: UUID) -> int:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            value = await session.scalar(
                select(func.count())
                .select_from(ExecutionWallet)
                .where(
                    ExecutionWallet.workspace_id == workspace_id,
                    ExecutionWallet.status == WalletStatus.ACTIVE,
                )
            )
            return int(value or 0)

    async def save_or_get(
        self,
        *,
        signer_result: SignerWalletResult,
        idempotency_key_hash: bytes,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> tuple[WalletRecord, bool]:
        wallet_id = uuid7()
        statement = (
            insert(ExecutionWallet)
            .values(
                id=wallet_id,
                workspace_id=signer_result.workspace_id,
                chain_id=signer_result.chain_id,
                address=signer_result.address,
                signer_key_id=signer_result.signer_key_id,
                idempotency_key_hash=idempotency_key_hash,
                status=WalletStatus.ACTIVE,
                balance_wei=Decimal(0),
            )
            .on_conflict_do_nothing(
                index_elements=[ExecutionWallet.workspace_id, ExecutionWallet.idempotency_key_hash]
            )
            .returning(ExecutionWallet)
        )
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, signer_result.workspace_id)
            created = (await session.execute(statement)).scalar_one_or_none()
            if created is not None:
                session.add(
                    AuditLog(
                        workspace_id=signer_result.workspace_id,
                        actor_type=ActorType.TELEGRAM_USER,
                        actor_id=str(actor_user_id),
                        action="execution_wallet_created",
                        resource_type="execution_wallet",
                        resource_id=str(wallet_id),
                        before=None,
                        after={
                            "chain_id": signer_result.chain_id,
                            "address": signer_result.address,
                            "signer_key_id": str(signer_result.signer_key_id),
                        },
                        correlation_id=correlation_id,
                        severity=Severity.HIGH,
                    )
                )
                return wallet_record(created), True
            existing = await session.scalar(
                select(ExecutionWallet).where(
                    ExecutionWallet.workspace_id == signer_result.workspace_id,
                    ExecutionWallet.idempotency_key_hash == idempotency_key_hash,
                )
            )
            if existing is None:
                raise RuntimeError("wallet idempotency conflict was not recoverable")
            return wallet_record(existing), False

    async def list_wallets(self, *, workspace_id: UUID) -> list[WalletRecord]:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            models = (
                await session.scalars(
                    select(ExecutionWallet)
                    .where(ExecutionWallet.workspace_id == workspace_id)
                    .order_by(ExecutionWallet.created_at.asc())
                )
            ).all()
            return [wallet_record(model) for model in models]

    async def find_by_id(self, *, workspace_id: UUID, wallet_id: UUID) -> WalletRecord | None:
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            model = await session.scalar(
                select(ExecutionWallet).where(
                    ExecutionWallet.workspace_id == workspace_id,
                    ExecutionWallet.id == wallet_id,
                )
            )
            return wallet_record(model) if model else None

    async def update_balance(
        self,
        *,
        workspace_id: UUID,
        wallet_id: UUID,
        balance_wei: int,
        block_number: int,
        refreshed_at: datetime,
    ) -> bool:
        if balance_wei < 0 or block_number < 0:
            raise ValueError("balance and block number must be non-negative")
        statement = (
            update(ExecutionWallet)
            .where(
                ExecutionWallet.workspace_id == workspace_id,
                ExecutionWallet.id == wallet_id,
                or_(
                    ExecutionWallet.balance_block_number.is_(None),
                    ExecutionWallet.balance_block_number <= block_number,
                ),
            )
            .values(
                balance_wei=Decimal(balance_wei),
                balance_block_number=block_number,
                balance_refreshed_at=refreshed_at,
                updated_at=func.now(),
            )
            .returning(ExecutionWallet.id)
        )
        async with self._sessions() as session, session.begin():
            await set_workspace_context(session, workspace_id)
            return (await session.scalar(statement)) is not None
