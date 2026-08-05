"""Authenticated private-network client for the CopyMint signer."""

from datetime import UTC, datetime
from uuid import UUID

import httpx
from pydantic import BaseModel

from app.application.wallets.ports import SignerWalletResult
from app.domain.ids import uuid7
from app.signer.auth import SignerClaims, sign_claims


class SignerWalletResponse(BaseModel):
    signer_key_id: UUID
    workspace_id: UUID
    chain_id: int
    address: str
    created: bool


class HttpSignerWalletClient:
    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self._base_url = base_url.rstrip("/")
        self._secret = auth_secret
        self._timeout = timeout_seconds
        self._transport = transport

    async def create_wallet(
        self,
        *,
        workspace_id: UUID,
        chain_id: int,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> SignerWalletResult:
        issued_at = datetime.now(tz=UTC)
        request_id = uuid7()
        body = {
            "workspace_id": str(workspace_id),
            "chain_id": chain_id,
            "idempotency_key": idempotency_key,
            "correlation_id": str(correlation_id),
        }
        claims = SignerClaims(
            action="wallet.create",
            caller="bot-api",
            workspace_id=workspace_id,
            chain_id=chain_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            issued_at=issued_at,
        )
        headers = {
            "X-CopyMint-Caller": claims.caller,
            "X-CopyMint-Request-ID": str(request_id),
            "X-CopyMint-Timestamp": str(int(issued_at.timestamp())),
            "X-CopyMint-Signature": sign_claims(self._secret, claims, body),
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(f"{self._base_url}/v1/wallets", json=body, headers=headers)
        response.raise_for_status()
        parsed = SignerWalletResponse.model_validate(response.json())
        return SignerWalletResult(**parsed.model_dump())
