"""Sanitized non-mutating Chainstack Ethereum capability probe."""

import asyncio
import json
import platform

from pydantic import ValidationError
from websockets.asyncio.client import connect

from app.application.ethereum.collections import EthereumCollectionDiscovery
from app.application.ethereum.decoders import ERC721_TRANSFER_TOPIC
from app.application.ethereum.ports import ProviderError
from app.infrastructure.config import get_ethereum_provider_settings
from app.infrastructure.ethereum import JsonRpcEvmProvider

REFERENCE_TRANSFER_CONTRACT = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
PROBE_LOG_BLOCKS = 10
PROBE_STAGE = "configuration"


async def run() -> bool:
    global PROBE_STAGE
    settings = get_ethereum_provider_settings()
    provider = JsonRpcEvmProvider(endpoint=settings.chainstack_ethereum_http_url.get_secret_value())
    PROBE_STAGE = "chain_id"
    await EthereumCollectionDiscovery(provider, chain_id=settings.ethereum_chain_id).verify_chain()
    PROBE_STAGE = "finality_tags"
    safe = await provider.block("safe")
    finalized = await provider.block("finalized")
    code = await provider.code(REFERENCE_TRANSFER_CONTRACT, finalized.number)
    if not code:
        raise RuntimeError("reference contract has no code at finalized boundary")
    PROBE_STAGE = "single_block_get_logs"
    await provider.logs(
        address=REFERENCE_TRANSFER_CONTRACT,
        start_block=finalized.number,
        end_block=finalized.number,
        topics=(ERC721_TRANSFER_TOPIC,),
    )
    PROBE_STAGE = "bounded_get_logs"
    logs = await provider.logs(
        address=REFERENCE_TRANSFER_CONTRACT,
        start_block=max(0, finalized.number - PROBE_LOG_BLOCKS + 1),
        end_block=finalized.number,
        topics=(ERC721_TRANSFER_TOPIC,),
    )
    if not logs:
        raise RuntimeError("reference ERC-721 produced no recent Transfer evidence")
    PROBE_STAGE = "transaction"
    transaction = await provider.transaction(logs[0].transaction_hash)
    PROBE_STAGE = "receipt"
    receipt = await provider.receipt(logs[0].transaction_hash)
    PROBE_STAGE = "debug_trace_transaction"
    trace_status = "passed"
    try:
        trace = await provider.trace_transaction(logs[0].transaction_hash)
    except ProviderError as exc:
        if exc.code != "http_403":
            raise
        trace_status = "unavailable_http_403"
    else:
        if not trace:
            raise RuntimeError("trace evidence is empty")
    if transaction.block_number != receipt.block_number:
        raise RuntimeError("transaction and receipt evidence is inconsistent")

    websocket_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_subscribe",
        "params": ["newHeads"],
    }
    PROBE_STAGE = "wss_new_heads"
    async with connect(
        settings.chainstack_ethereum_wss_url.get_secret_value(),
        open_timeout=15,
        close_timeout=5,
    ) as websocket:
        await websocket.send(json.dumps(websocket_request))
        response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=15))
        if not isinstance(response, dict) or not isinstance(response.get("result"), str):
            raise RuntimeError("Chainstack newHeads subscription was rejected")
        subscription_id = response["result"]
        await websocket.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "eth_unsubscribe",
                    "params": [subscription_id],
                }
            )
        )
        await asyncio.wait_for(websocket.recv(), timeout=15)

    print(
        json.dumps(
            {
                "result": "passed" if trace_status == "passed" else "partial",
                "chain_id": settings.ethereum_chain_id,
                "safe_block": safe.number,
                "finalized_block": finalized.number,
                "finality_order": "passed" if safe.number >= finalized.number else "failed",
                "reference_contract_code": "present",
                "bounded_get_logs": "passed",
                "transaction_and_receipt": "passed",
                "debug_trace_transaction": trace_status,
                "wss_new_heads_subscription": "passed",
            },
            sort_keys=True,
        )
    )
    return trace_status == "passed"


def main() -> None:
    try:
        if platform.system() == "Windows":
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                complete = runner.run(run())
            if not complete:
                raise SystemExit(2)
            return
        if not asyncio.run(run()):
            raise SystemExit(2)
    except Exception as exc:
        result: dict[str, object] = {
            "result": "failed",
            "stage": PROBE_STAGE,
            "error_type": type(exc).__name__,
        }
        if isinstance(exc, ProviderError):
            result["provider_code"] = exc.code
        elif isinstance(exc, ValidationError):
            result["configuration_errors"] = [
                {
                    "field": ".".join(str(part) for part in error["loc"]),
                    "type": error["type"],
                }
                for error in exc.errors()
            ]
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
