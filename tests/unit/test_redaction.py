import json
import logging

from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.observability.redaction import REDACTED, redact, redact_text


def test_recursive_redaction_keeps_public_provenance() -> None:
    tx_hash = "0x" + "ab" * 32
    fake_token = "123456:abcdefghijklmnopqrstuvwxyzABCD"  # secret-scan: allow-test-fixture
    payload = {
        "tx_hash": tx_hash,
        "telegram_bot_token": fake_token,
        "nested": {"private_key": "0x" + "11" * 32, "chain_id": 1},
    }
    assert redact(payload) == {
        "tx_hash": tx_hash,
        "telegram_bot_token": REDACTED,
        "nested": {"private_key": REDACTED, "chain_id": 1},
    }


def test_free_form_redaction_covers_common_credentials() -> None:
    text = (
        "Authorization Bearer abc.def-123 "
        "postgresql://user:password@db.internal/copymint "
        "api_key=super-secret private_key=0xdeadbeef"
    )
    result = redact_text(text)
    assert "abc.def-123" not in result
    assert "user:password" not in result
    assert "super-secret" not in result
    assert "0xdeadbeef" not in result
    assert result.count(REDACTED) >= 4


def test_json_logging_redacts_before_output(capsys: object) -> None:
    configure_logging("INFO")
    logging.getLogger("test").info(
        "request %s",
        {"authorization": "Bearer should-not-appear", "chain_id": 1},
        extra={"event": "provider_request", "chain_id": 1},
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    line = json.loads(captured.err)
    assert line["event"] == "provider_request"
    assert line["chain_id"] == 1
    assert "should-not-appear" not in line["message"]
    assert REDACTED in line["message"]
