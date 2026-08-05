"""Minimal Ethereum JSON-RPC client for safe wallet balance snapshots."""

from typing import Any

import httpx


class ChainstackEthereumBalanceClient:
    def __init__(
        self,
        *,
        endpoint: str,
        chain_id: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._chain_id = chain_id
        self._transport = transport

    async def _rpc(self, method: str, params: list[object]) -> str:
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            response = await client.post(
                self._endpoint,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict) or payload.get("error") is not None:
            raise RuntimeError("Ethereum RPC request failed")
        result = payload.get("result")
        if not isinstance(result, str) or not result.startswith("0x"):
            raise RuntimeError("Ethereum RPC returned an invalid hexadecimal result")
        return result

    async def balance_at_latest_block(self, *, address: str) -> tuple[int, int]:
        observed_chain_id = int(await self._rpc("eth_chainId", []), 16)
        if observed_chain_id != self._chain_id:
            raise RuntimeError("Ethereum RPC chain ID does not match configured chain")
        block_number = int(await self._rpc("eth_blockNumber", []), 16)
        balance = int(await self._rpc("eth_getBalance", [address, hex(block_number)]), 16)
        return balance, block_number
