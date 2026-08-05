"""Celery factory with conservative at-least-once worker defaults."""

from celery import Celery

from app.infrastructure.config import WorkerSettings, get_worker_settings
from app.workers import provider_guard as _provider_guard  # noqa: F401


def create_celery_app(settings: WorkerSettings | None = None) -> Celery:
    runtime_settings = settings or get_worker_settings()
    broker_url = runtime_settings.queue_url.get_secret_value()
    application = Celery("copymint", broker=broker_url)
    application.conf.update(
        accept_content=["json"],
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": 1800},
        enable_utc=True,
        imports=("app.workers.wallet_balances",),
        result_backend=None,
        task_acks_late=True,
        task_default_queue="maintenance",
        task_ignore_result=True,
        task_reject_on_worker_lost=True,
        task_serializer="json",
        task_soft_time_limit=840,
        task_time_limit=900,
        timezone="UTC",
        worker_prefetch_multiplier=1,
    )
    return application


celery_app = create_celery_app()
