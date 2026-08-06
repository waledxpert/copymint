import os
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("QUEUE_URL", "redis://localhost:6379/0")
os.environ.setdefault("CHAINSTACK_ETHEREUM_HTTP_URL", "https://example.invalid/rpc")
os.environ.setdefault("CHAINSTACK_ETHEREUM_WSS_URL", "wss://example.invalid/rpc")

from app.workers import collections


def test_incomplete_scan_requeues_the_same_opaque_collection(monkeypatch: object) -> None:
    collection_id = str(uuid4())
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(  # type: ignore[attr-defined]
        collections,
        "run_scan",
        lambda parsed: collections.ScanSliceResult(completed=False),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        collections.celery_app,
        "send_task",
        lambda name, **values: sent.append((name, values)),
    )

    assert collections.scan_collection(collection_id=collection_id) is False
    assert sent == [
        (
            "copymint.ethereum.scan_collection",
            {"kwargs": {"collection_id": collection_id}, "queue": "indexer"},
        )
    ]


def test_completed_scan_does_not_enqueue_another_slice(monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        collections,
        "run_scan",
        lambda parsed: collections.ScanSliceResult(completed=True),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        collections.celery_app,
        "send_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected enqueue")),
    )

    assert collections.scan_collection(collection_id=str(uuid4())) is True
