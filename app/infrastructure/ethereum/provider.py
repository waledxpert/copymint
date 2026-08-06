"""Credential-safe Ethereum JSON-RPC provider adapter."""

from typing import Any

import httpx

from app.application.ethereum.ports import (
    BlockReference,
    EvmLog,
    EvmReceipt,
    EvmTransaction,
    ProviderError,
)


def quantity(value: object, field: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ProviderError(f"invalid_{field}", transient=False)
    return int(value, 16)


class JsonRpcEvmProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        alias: str = "chainstack-primary",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self.alias = alias
        self._transport = transport
        self._request_id = 0

    async def _rpc(self, method: str, params: list[object]) -> Any:
        self._request_id += 1
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=20.0) as client:
                response = await client.post(
                    self._endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "id": self._request_id,
                        "method": method,
                        "params": params,
                    },
                )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ProviderError("transport", transient=True) from None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            split_range = method == "eth_getLogs" and status == 403
            raise ProviderError(
                f"http_{status}",
                transient=split_range or status == 429 or status >= 500,
                split_range=split_range,
            ) from None
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("invalid_response", transient=False)
        error = payload.get("error")
        if isinstance(error, dict):
            rpc_code = error.get("code")
            split = rpc_code in {-32005, -32602}
            raise ProviderError(f"rpc_{rpc_code}", transient=split, split_range=split)
        if "result" not in payload:
            raise ProviderError("missing_result", transient=False)
        return payload["result"]

    async def chain_id(self) -> int:
        return quantity(await self._rpc("eth_chainId", []), "chain_id")

    async def block(self, tag: int | str) -> BlockReference:
        block_tag = hex(tag) if isinstance(tag, int) else tag
        result = await self._rpc("eth_getBlockByNumber", [block_tag, False])
        if not isinstance(result, dict) or not isinstance(result.get("hash"), str):
            raise ProviderError("invalid_block", transient=False)
        return BlockReference(
            number=quantity(result.get("number"), "block_number"),
            block_hash=result["hash"],
        )

    async def code(self, address: str, block: int | str = "latest") -> bytes:
        block_tag = hex(block) if isinstance(block, int) else block
        result = await self._rpc("eth_getCode", [address, block_tag])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise ProviderError("invalid_code", transient=False)
        try:
            return bytes.fromhex(result[2:])
        except ValueError:
            raise ProviderError("invalid_code", transient=False) from None

    async def storage_at(self, address: str, slot: str, block: int | str) -> bytes:
        block_tag = hex(block) if isinstance(block, int) else block
        result = await self._rpc("eth_getStorageAt", [address, slot, block_tag])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise ProviderError("invalid_storage", transient=False)
        try:
            value = bytes.fromhex(result[2:])
        except ValueError:
            raise ProviderError("invalid_storage", transient=False) from None
        if len(value) != 32:
            raise ProviderError("invalid_storage", transient=False)
        return value

    async def logs(
        self,
        *,
        address: str,
        start_block: int,
        end_block: int,
        topics: tuple[str | None, ...] = (),
    ) -> list[EvmLog]:
        if start_block < 0 or end_block < start_block:
            raise ValueError("invalid log block range")
        query: dict[str, object] = {
            "address": address,
            "fromBlock": hex(start_block),
            "toBlock": hex(end_block),
        }
        if topics:
            query["topics"] = list(topics)
        result = await self._rpc("eth_getLogs", [query])
        if not isinstance(result, list):
            raise ProviderError("invalid_logs", transient=False)
        logs: list[EvmLog] = []
        for item in result:
            if not isinstance(item, dict) or not isinstance(item.get("topics"), list):
                raise ProviderError("invalid_log", transient=False)
            logs.append(
                EvmLog(
                    address=str(item["address"]),
                    topics=tuple(str(topic) for topic in item["topics"]),
                    data=str(item["data"]),
                    block_number=quantity(item.get("blockNumber"), "block_number"),
                    block_hash=str(item["blockHash"]),
                    transaction_hash=str(item["transactionHash"]),
                    log_index=quantity(item.get("logIndex"), "log_index"),
                    removed=bool(item.get("removed", False)),
                )
            )
        return logs

    async def transaction(self, transaction_hash: str) -> EvmTransaction:
        result = await self._rpc("eth_getTransactionByHash", [transaction_hash])
        if not isinstance(result, dict):
            raise ProviderError("transaction_not_found", transient=False)
        recipient = result.get("to")
        return EvmTransaction(
            transaction_hash=str(result["hash"]),
            sender=str(result["from"]),
            recipient=str(recipient) if recipient is not None else None,
            value_wei=quantity(result.get("value"), "transaction_value"),
            input_data=str(result["input"]),
            block_number=quantity(result.get("blockNumber"), "block_number"),
        )

    async def receipt(self, transaction_hash: str) -> EvmReceipt:
        result = await self._rpc("eth_getTransactionReceipt", [transaction_hash])
        if not isinstance(result, dict):
            raise ProviderError("receipt_not_found", transient=True)
        gas_price = result.get("effectiveGasPrice")
        return EvmReceipt(
            transaction_hash=str(result["transactionHash"]),
            block_number=quantity(result.get("blockNumber"), "block_number"),
            block_hash=str(result["blockHash"]),
            status=quantity(result.get("status"), "receipt_status"),
            gas_used=quantity(result.get("gasUsed"), "gas_used"),
            effective_gas_price=(
                quantity(gas_price, "effective_gas_price") if gas_price is not None else None
            ),
        )

    async def trace_transaction(self, transaction_hash: str) -> dict[str, object]:
        result = await self._rpc(
            "debug_traceTransaction",
            [transaction_hash, {"tracer": "callTracer", "timeout": "10s"}],
        )
        if not isinstance(result, dict):
            raise ProviderError("invalid_trace", transient=False)
        return result
