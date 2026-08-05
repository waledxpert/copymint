"""Central recursive redaction for logs and diagnostics."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_FRAGMENTS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "bot_token",
        "ciphertext",
        "cookie",
        "database_url",
        "encrypted_data_key",
        "kms",
        "mnemonic",
        "password",
        "private_key",
        "queue_url",
        "raw_transaction",
        "recovery",
        "rpc_url",
        "seed",
        "secret",
        "signed_transaction",
        "signer_key_id",
        "token",
    }
)

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_CREDENTIAL_URL_RE = re.compile(
    r"(?i)\b(?P<scheme>postgres(?:ql)?(?:\+\w+)?|redis(?:s)?)://[^\s/@]+:[^\s/@]+@"
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)(?P<name>api[_-]?key|access[_-]?token|token|secret|key)=(?P<value>[^&\s]+)"
)
_LABELED_SECRET_RE = re.compile(
    r"(?i)(?P<label>private[_ -]?key|seed[_ -]?phrase|mnemonic|password|secret)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^,;\s]+)"
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_").replace(" ", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def redact_text(value: str) -> str:
    """Redact common credential shapes from free-form text."""
    redacted = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    redacted = _TELEGRAM_TOKEN_RE.sub(REDACTED, redacted)
    redacted = _CREDENTIAL_URL_RE.sub(
        lambda match: f"{match.group('scheme')}://{REDACTED}@", redacted
    )
    redacted = _QUERY_SECRET_RE.sub(lambda match: f"{match.group('name')}={REDACTED}", redacted)
    return _LABELED_SECRET_RE.sub(
        lambda match: f"{match.group('label')}{match.group('separator')}{REDACTED}", redacted
    )


def redact(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact structured values while preserving useful public context."""
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact(item) for item in value]
    return value
