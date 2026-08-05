import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.domain.ids import uuid7
from app.infrastructure.signer_client import HttpSignerWalletClient
from app.signer.auth import SignerClaims, verify_claims


@pytest.mark.asyncio
async def test_signer_client_authenticates_the_exact_wallet_request() -> None:
    secret = "s" * 32
    workspace_id = uuid7()
    correlation_id = uuid7()

    async def signer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        claims = SignerClaims(
            action="wallet.create",
            caller=request.headers["X-CopyMint-Caller"],
            workspace_id=workspace_id,
            chain_id=body["chain_id"],
            idempotency_key=body["idempotency_key"],
            correlation_id=correlation_id,
            request_id=UUID(request.headers["X-CopyMint-Request-ID"]),
            issued_at=datetime.fromtimestamp(
                int(request.headers["X-CopyMint-Timestamp"]),
                tz=UTC,
            ),
        )
        verify_claims(secret, claims, body, request.headers["X-CopyMint-Signature"])
        return httpx.Response(
            200,
            json={
                "signer_key_id": str(uuid7()),
                "workspace_id": str(workspace_id),
                "chain_id": 1,
                "address": "0x1111111111111111111111111111111111111111",
                "created": True,
            },
        )

    client = HttpSignerWalletClient(
        base_url="signer:10000",
        auth_secret=secret,
        transport=httpx.MockTransport(signer),
    )
    result = await client.create_wallet(
        workspace_id=workspace_id,
        chain_id=1,
        idempotency_key="wallet-request-001",
        correlation_id=correlation_id,
    )
    assert result.workspace_id == workspace_id
    assert result.created
