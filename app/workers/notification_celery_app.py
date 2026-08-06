"""Celery application isolated to Telegram notification credentials."""

from celery import Celery

from app.infrastructure.config import get_notification_worker_settings

settings = get_notification_worker_settings()
notification_celery_app = Celery(
    "copymint-notifications", broker=settings.queue_url.get_secret_value()
)
notification_celery_app.conf.update(
    accept_content=["json"],
    enable_utc=True,
    imports=("app.workers.scan_notifications",),
    result_backend=None,
    task_acks_late=True,
    task_default_queue="notifications",
    task_ignore_result=True,
    task_serializer="json",
    timezone="UTC",
    worker_prefetch_multiplier=1,
)
