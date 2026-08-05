"""Timestamped HMAC authentication for private signer requests."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID


class SignerAuthenticationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SignerClaims:
    action: str
    caller: str
    workspace_id: UUID
    chain_id: int
    idempotency_key: str
    correlation_id: UUID
    request_id: UUID
    issued_at: datetime


def canonical_body(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def canonical_claims(claims: SignerClaims, body: dict[str, Any]) -> bytes:
    parts = (
        claims.action,
        claims.caller,
        str(claims.workspace_id),
        str(claims.chain_id),
        claims.idempotency_key,
        str(claims.correlation_id),
        str(claims.request_id),
        str(int(claims.issued_at.timestamp())),
        hashlib.sha256(canonical_body(body)).hexdigest(),
    )
    return "\n".join(parts).encode("utf-8")


def sign_claims(secret: str, claims: SignerClaims, body: dict[str, Any]) -> str:
    return hmac.new(
        secret.encode("utf-8"), canonical_claims(claims, body), hashlib.sha256
    ).hexdigest()


def verify_claims(
    secret: str,
    claims: SignerClaims,
    body: dict[str, Any],
    signature: str,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(seconds=60),
) -> None:
    current = now or datetime.now(tz=UTC)
    if claims.issued_at.tzinfo is None:
        raise SignerAuthenticationError("signer timestamp must include a timezone")
    age = current - claims.issued_at
    if age < -timedelta(seconds=5) or age > max_age:
        raise SignerAuthenticationError("signer request is expired")
    expected = sign_claims(secret, claims, body)
    if len(signature) != 64 or not hmac.compare_digest(signature, expected):
        raise SignerAuthenticationError("signer request authentication failed")
