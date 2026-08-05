from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.ids import uuid7
from app.signer.api import SignerRuntime, create_app
from app.signer.auth import SignerClaims, sign_claims
from app.signer.service import WalletDescriptor

SECRET = "s" * 32


class FakeWalletService:
    def __init__(self) -> None:
        self.key_id = uuid7()
        self.calls = 0

    async def create_wallet(self, **values: Any) -> WalletDescriptor:
        self.calls += 1
        return WalletDescriptor(
            signer_key_id=self.key_id,
            workspace_id=values["workspace_id"],
            chain_id=values["chain_id"],
            address="0x1111111111111111111111111111111111111111",
            created=True,
        )

    async def verify_restore(self, **values: Any) -> str:
        if values["signer_key_id"] != self.key_id:
            raise LookupError
        return "0x1111111111111111111111111111111111111111"


class FakeReplayRepository:
    def __init__(self) -> None:
        self.claims: set[UUID] = set()

    async def claim(self, *, request_id: UUID, expires_at: datetime) -> bool:
        if request_id in self.claims:
            return False
        self.claims.add(request_id)
        return True


def signed_request(*, action: str, workspace_id: UUID, body: dict[str, Any]) -> dict[str, str]:
    issued_at = datetime.now(tz=UTC)
    claims = SignerClaims(
        action=action,
        caller="bot-api",
        workspace_id=workspace_id,
        chain_id=body["chain_id"],
        idempotency_key=body["idempotency_key"],
        correlation_id=UUID(body["correlation_id"]),
        request_id=uuid7(),
        issued_at=issued_at,
    )
    return {
        "X-CopyMint-Caller": claims.caller,
        "X-CopyMint-Request-ID": str(claims.request_id),
        "X-CopyMint-Timestamp": str(int(issued_at.timestamp())),
        "X-CopyMint-Signature": sign_claims(SECRET, claims, body),
    }


@pytest.mark.asyncio
async def test_wallet_creation_requires_valid_bound_signature_and_rejects_replay() -> None:
    service = FakeWalletService()
    runtime = SignerRuntime(
        wallet_service=service,  # type: ignore[arg-type]
        replay_repository=FakeReplayRepository(),
        auth_secret=SECRET,
        environment="test",
    )
    app = create_app(runtime)
    workspace_id = uuid7()
    body = {
        "workspace_id": str(workspace_id),
        "chain_id": 1,
        "idempotency_key": "request-00000001",
        "correlation_id": str(uuid7()),
    }
    headers = signed_request(action="wallet.create", workspace_id=workspace_id, body=body)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://signer") as client:
        created = await client.post("/v1/wallets", json=body, headers=headers)
        replayed = await client.post("/v1/wallets", json=body, headers=headers)
        tampered = await client.post(
            "/v1/wallets", json={**body, "idempotency_key": "tampered-0000001"}, headers=headers
        )

    assert created.status_code == 200
    assert created.json()["address"] == "0x1111111111111111111111111111111111111111"
    assert replayed.status_code == 409
    assert tampered.status_code == 401
    assert service.calls == 1


@pytest.mark.asyncio
async def test_restore_verification_is_unavailable_in_production() -> None:
    runtime = SignerRuntime(
        wallet_service=FakeWalletService(),  # type: ignore[arg-type]
        replay_repository=FakeReplayRepository(),
        auth_secret=SECRET,
        environment="production",
    )
    app = create_app(runtime)
    body = {
        "signer_key_id": str(uuid7()),
        "workspace_id": str(uuid7()),
        "chain_id": 1,
        "idempotency_key": "restore-00000001",
        "correlation_id": str(uuid7()),
    }
    headers = signed_request(
        action="wallet.restore", workspace_id=UUID(body["workspace_id"]), body=body
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://signer") as client:
        response = await client.post("/v1/restore/verify", json=body, headers=headers)
    assert response.status_code == 404
