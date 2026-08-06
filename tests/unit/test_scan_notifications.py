import os
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("QUEUE_URL", "redis://localhost:6379/0")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "000000000:test-token")

from app.workers import scan_notifications


def test_nonterminal_notification_requeues_opaque_identifiers(monkeypatch: object) -> None:
    workspace_id = str(uuid4())
    collection_id = str(uuid4())
    sent: list[tuple[str, dict[str, object]]] = []

    def finish_without_running(coroutine: object) -> scan_notifications.NotificationResult:
        coroutine.close()  # type: ignore[attr-defined]
        return scan_notifications.NotificationResult(terminal=False)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        scan_notifications.asyncio,
        "run",
        finish_without_running,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        scan_notifications.notification_celery_app,
        "send_task",
        lambda name, **values: sent.append((name, values)),
    )
    assert not scan_notifications.track_scan(workspace_id=workspace_id, collection_id=collection_id)
    assert sent[0][1]["countdown"] == 60
    assert sent[0][1]["kwargs"] == {
        "workspace_id": workspace_id,
        "collection_id": collection_id,
    }
