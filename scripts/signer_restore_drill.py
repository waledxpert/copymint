"""Run a sanitized, non-production AWS KMS signer restore drill."""

import argparse
import asyncio
import json
import platform
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.ids import uuid7
from app.infrastructure.config import get_signer_settings
from app.infrastructure.db.session import normalize_database_url
from app.signer.kms import AwsKmsDataKeyProvider
from app.signer.service import SignerWalletService
from app.signer.storage import SqlAlchemySignerEnvelopeRepository


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subcommands = value.add_subparsers(dest="command", required=True)
    subcommands.add_parser("create")
    verify = subcommands.add_parser("verify")
    verify.add_argument("--signer-key-id", required=True, type=UUID)
    verify.add_argument("--workspace-id", required=True, type=UUID)
    verify.add_argument("--expected-address", required=True)
    return value


async def run(args: argparse.Namespace) -> None:
    settings = get_signer_settings()
    if settings.app_env == "production":
        raise RuntimeError("restore drills are forbidden in production")
    engine = create_async_engine(
        normalize_database_url(settings.signer_database_url.get_secret_value()),
        pool_pre_ping=True,
    )
    kms = AwsKmsDataKeyProvider(
        boto3.client("kms", region_name=settings.aws_region, **settings.aws_client_credentials()),
        key_arn=settings.aws_kms_key_arn.get_secret_value(),
    )
    service = SignerWalletService(
        SqlAlchemySignerEnvelopeRepository(async_sessionmaker(engine, expire_on_commit=False)),
        kms,
        environment=settings.app_env,
    )
    try:
        if not await kms.health():
            raise RuntimeError("configured KMS key is not enabled for encryption/decryption")
        if args.command == "create":
            workspace_id = uuid7()
            idempotency_key = f"kms-restore-drill-{uuid7()}"
            wallet = await service.create_wallet(
                workspace_id=workspace_id,
                chain_id=1,
                idempotency_key=idempotency_key,
            )
            repeated = await service.create_wallet(
                workspace_id=workspace_id,
                chain_id=1,
                idempotency_key=idempotency_key,
            )
            restored = await service.verify_restore(
                signer_key_id=wallet.signer_key_id,
                workspace_id=workspace_id,
                chain_id=1,
            )
            if repeated.signer_key_id != wallet.signer_key_id or restored != wallet.address:
                raise RuntimeError("idempotency or address verification failed")
            try:
                await service.verify_restore(
                    signer_key_id=wallet.signer_key_id,
                    workspace_id=uuid7(),
                    chain_id=1,
                )
            except LookupError:
                isolation = "passed"
            else:
                raise RuntimeError("cross-workspace restore was not rejected")
            print(
                json.dumps(
                    {
                        "result": "passed",
                        "kms_health": "passed",
                        "idempotency": "passed",
                        "workspace_isolation": isolation,
                        "signer_key_id": str(wallet.signer_key_id),
                        "workspace_id": str(workspace_id),
                        "expected_address": wallet.address,
                    },
                    sort_keys=True,
                )
            )
            return
        restored = await service.verify_restore(
            signer_key_id=args.signer_key_id,
            workspace_id=args.workspace_id,
            chain_id=1,
        )
        if restored != args.expected_address:
            raise RuntimeError("restored address does not match expected address")
        print(json.dumps({"result": "passed", "expected_address": restored}, sort_keys=True))
    finally:
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        if platform.system() == "Windows":
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                runner.run(run(args))
            return
        asyncio.run(run(args))
    except Exception as exc:
        print(json.dumps({"result": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
