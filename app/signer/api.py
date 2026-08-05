"""Private signer API; wallet creation only, with signing release-locked off."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Protocol
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app import __version__
from app.domain.release import signing_is_available
from app.infrastructure.config import SignerSettings, get_signer_settings
from app.infrastructure.db.session import normalize_database_url
from app.infrastructure.observability import configure_logging
from app.signer.auth import (
    SignerAuthenticationError,
    SignerClaims,
    verify_claims,
)
from app.signer.kms import AwsKmsDataKeyProvider
from app.signer.service import SignerWalletService, WalletDescriptor
from app.signer.storage import (
    SqlAlchemySignerEnvelopeRepository,
    SqlAlchemySignerReplayRepository,
)

AUTH_MAX_AGE = timedelta(seconds=60)


class ReplayRepository(Protocol):
    async def claim(self, *, request_id: UUID, expires_at: datetime) -> bool: ...


@dataclass(slots=True)
class SignerRuntime:
    wallet_service: SignerWalletService
    replay_repository: ReplayRepository
    auth_secret: str
    environment: str
    engine: AsyncEngine | None = None
    kms: AwsKmsDataKeyProvider | None = None


class SignerHealth(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    wallet_creation: Literal["enabled"] = "enabled"
    signing: Literal["disabled"] = "disabled"


class CreateWalletRequest(BaseModel):
    workspace_id: UUID
    chain_id: Literal[1] = 1
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID


class WalletResponse(BaseModel):
    signer_key_id: UUID
    workspace_id: UUID
    chain_id: Literal[1]
    address: str
    created: bool


class RestoreRequest(BaseModel):
    signer_key_id: UUID
    workspace_id: UUID
    chain_id: Literal[1] = 1
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID


def create_runtime(settings: SignerSettings) -> SignerRuntime:
    engine = create_async_engine(
        normalize_database_url(settings.signer_database_url.get_secret_value()),
        pool_pre_ping=True,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    kms_client = boto3.client(
        "kms",
        region_name=settings.aws_region,
        **settings.aws_client_credentials(),
    )
    kms = AwsKmsDataKeyProvider(kms_client, key_arn=settings.aws_kms_key_arn.get_secret_value())
    return SignerRuntime(
        wallet_service=SignerWalletService(
            SqlAlchemySignerEnvelopeRepository(sessions), kms, environment=settings.app_env
        ),
        replay_repository=SqlAlchemySignerReplayRepository(sessions),
        auth_secret=settings.signer_auth_secret.get_secret_value(),
        environment=settings.app_env,
        engine=engine,
        kms=kms,
    )


def runtime_from(request: Request) -> SignerRuntime:
    runtime: SignerRuntime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:
        runtime = create_runtime(request.app.state.settings)
        request.app.state.runtime = runtime
    return runtime


def request_body(model: BaseModel) -> dict[str, object]:
    return model.model_dump(mode="json")


async def authenticate(
    *,
    runtime: SignerRuntime,
    action: str,
    body: CreateWalletRequest | RestoreRequest,
    caller: str,
    request_id: UUID,
    timestamp: int,
    signature: str,
) -> None:
    claims = SignerClaims(
        action=action,
        caller=caller,
        workspace_id=body.workspace_id,
        chain_id=body.chain_id,
        idempotency_key=body.idempotency_key,
        correlation_id=body.correlation_id,
        request_id=request_id,
        issued_at=datetime.fromtimestamp(timestamp, tz=UTC),
    )
    try:
        verify_claims(runtime.auth_secret, claims, request_body(body), signature)
    except (SignerAuthenticationError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "signer_authentication_failed"},
        ) from exc
    claimed = await runtime.replay_repository.claim(
        request_id=request_id, expires_at=claims.issued_at + AUTH_MAX_AGE
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "signer_request_replayed"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_signer_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    try:
        yield
    finally:
        runtime: SignerRuntime | None = getattr(app.state, "runtime", None)
        if runtime is not None and runtime.engine is not None:
            await runtime.engine.dispose()


def create_app(runtime: SignerRuntime | None = None) -> FastAPI:
    application = FastAPI(
        title="CopyMint Signer",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    if runtime is not None:
        application.state.runtime = runtime

    @application.get("/health/live", response_model=SignerHealth)
    async def liveness() -> SignerHealth:
        return SignerHealth(version=__version__)

    @application.get("/health/ready", response_model=SignerHealth)
    async def readiness(request: Request) -> SignerHealth:
        current = runtime_from(request)
        if current.engine is None or current.kms is None:
            return SignerHealth(version=__version__)
        try:
            sessions = async_sessionmaker(current.engine, expire_on_commit=False)
            async with sessions() as session:
                await session.execute(text("SELECT 1"))
            if not await current.kms.health():
                raise RuntimeError("KMS key is not enabled for encryption")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "signer_not_ready"},
            ) from exc
        return SignerHealth(version=__version__)

    @application.post("/v1/wallets", response_model=WalletResponse)
    async def create_wallet(
        body: CreateWalletRequest,
        request: Request,
        x_copymint_caller: Annotated[str, Header()],
        x_copymint_request_id: Annotated[UUID, Header()],
        x_copymint_timestamp: Annotated[int, Header()],
        x_copymint_signature: Annotated[str, Header()],
    ) -> WalletResponse:
        current = runtime_from(request)
        await authenticate(
            runtime=current,
            action="wallet.create",
            body=body,
            caller=x_copymint_caller,
            request_id=x_copymint_request_id,
            timestamp=x_copymint_timestamp,
            signature=x_copymint_signature,
        )
        descriptor: WalletDescriptor = await current.wallet_service.create_wallet(
            workspace_id=body.workspace_id,
            chain_id=body.chain_id,
            idempotency_key=body.idempotency_key,
        )
        return WalletResponse(
            signer_key_id=descriptor.signer_key_id,
            workspace_id=descriptor.workspace_id,
            chain_id=1,
            address=descriptor.address,
            created=descriptor.created,
        )

    @application.post("/v1/restore/verify", response_model=WalletResponse)
    async def verify_restore(
        body: RestoreRequest,
        request: Request,
        x_copymint_caller: Annotated[str, Header()],
        x_copymint_request_id: Annotated[UUID, Header()],
        x_copymint_timestamp: Annotated[int, Header()],
        x_copymint_signature: Annotated[str, Header()],
    ) -> WalletResponse:
        current = runtime_from(request)
        if current.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "restore_verification_unavailable"},
            )
        await authenticate(
            runtime=current,
            action="wallet.restore",
            body=body,
            caller=x_copymint_caller,
            request_id=x_copymint_request_id,
            timestamp=x_copymint_timestamp,
            signature=x_copymint_signature,
        )
        try:
            address = await current.wallet_service.verify_restore(
                signer_key_id=body.signer_key_id,
                workspace_id=body.workspace_id,
                chain_id=body.chain_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "signer_key_not_found"},
            ) from exc
        return WalletResponse(
            signer_key_id=body.signer_key_id,
            workspace_id=body.workspace_id,
            chain_id=body.chain_id,
            address=address,
            created=False,
        )

    @application.post("/v1/sign", include_in_schema=False, response_model=None)
    async def sign_release_locked() -> None:
        assert signing_is_available() is False
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "code": "release_locked",
                "message": "Signing is unavailable in CopyMint Release 1.",
            },
        )

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.signer.api:app", host="0.0.0.0", port=10000)  # noqa: S104


if __name__ == "__main__":
    run()
