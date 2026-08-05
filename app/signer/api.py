"""Private signer API; signing is release-locked off."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from app import __version__
from app.domain.release import signing_is_available
from app.infrastructure.config import get_signer_settings
from app.infrastructure.observability import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_signer_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    yield


class SignerHealth(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    wallet_creation: Literal["not_implemented"] = "not_implemented"
    signing: Literal["disabled"] = "disabled"


def create_app() -> FastAPI:
    application = FastAPI(
        title="CopyMint Signer",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.get("/health/live", response_model=SignerHealth)
    async def liveness() -> SignerHealth:
        return SignerHealth(version=__version__)

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
