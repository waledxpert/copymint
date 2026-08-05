"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes.health import router as health_router
from app.infrastructure.config import get_api_settings
from app.infrastructure.observability import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_api_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="CopyMint API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.include_router(health_router)
    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=10000)  # noqa: S104


if __name__ == "__main__":
    run()
