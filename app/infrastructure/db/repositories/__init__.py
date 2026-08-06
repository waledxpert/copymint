"""SQLAlchemy repository adapters."""

from app.infrastructure.db.repositories.access import (
    SqlAlchemyAccessRepository,
    SqlAlchemySecurityAudit,
)
from app.infrastructure.db.repositories.challenges import SqlAlchemyChallengeRepository
from app.infrastructure.db.repositories.collections import SqlAlchemyWorkspaceCollectionRepository
from app.infrastructure.db.repositories.ethereum import SqlAlchemyMintBatchConsumer
from app.infrastructure.db.repositories.telegram_updates import (
    SqlAlchemyTelegramUpdateRepository,
)
from app.infrastructure.db.repositories.wallets import SqlAlchemyWalletRepository

__all__ = [
    "SqlAlchemyAccessRepository",
    "SqlAlchemyChallengeRepository",
    "SqlAlchemyMintBatchConsumer",
    "SqlAlchemySecurityAudit",
    "SqlAlchemyTelegramUpdateRepository",
    "SqlAlchemyWalletRepository",
    "SqlAlchemyWorkspaceCollectionRepository",
]
