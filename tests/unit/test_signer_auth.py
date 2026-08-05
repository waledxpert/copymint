from datetime import UTC, datetime, timedelta

import pytest

from app.domain.ids import uuid7
from app.signer.auth import (
    SignerAuthenticationError,
    SignerClaims,
    sign_claims,
    verify_claims,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
SECRET = "s" * 32


def claims() -> SignerClaims:
    return SignerClaims(
        action="wallet.create",
        caller="bot-api",
        workspace_id=uuid7(),
        chain_id=1,
        idempotency_key="request-00000001",
        correlation_id=uuid7(),
        request_id=uuid7(),
        issued_at=NOW,
    )


def test_signer_authentication_binds_every_authoritative_field() -> None:
    value = claims()
    body = {"workspace_id": str(value.workspace_id), "chain_id": 1}
    signature = sign_claims(SECRET, value, body)
    verify_claims(SECRET, value, body, signature, now=NOW)

    with pytest.raises(SignerAuthenticationError):
        verify_claims(SECRET, value, {**body, "chain_id": 5}, signature, now=NOW)


def test_signer_authentication_rejects_expired_and_future_requests() -> None:
    value = claims()
    body = {"workspace_id": str(value.workspace_id), "chain_id": 1}
    signature = sign_claims(SECRET, value, body)
    with pytest.raises(SignerAuthenticationError, match="expired"):
        verify_claims(SECRET, value, body, signature, now=NOW + timedelta(seconds=61))
    with pytest.raises(SignerAuthenticationError, match="expired"):
        verify_claims(SECRET, value, body, signature, now=NOW - timedelta(seconds=6))
