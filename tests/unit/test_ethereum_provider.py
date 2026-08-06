import json

import httpx
import pytest

from app.application.ethereum.collections import EthereumCollectionDiscovery, InvalidCollection
from app.domain.enums import DeploymentConfidence
from app.infrastructure.ethereum.provider import JsonRpcEvmProvider, ProviderError

ADDRESS = "0x1111111111111111111111111111111111111111"


def rpc_transport(*, deployment_block: int = 7, chain_id: int = 1) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body["method"]
        params = body["params"]
        if method == "eth_chainId":
            result: object = hex(chain_id)
        elif method == "eth_getBlockByNumber":
            number = 20 if params[0] == "finalized" else int(params[0], 16)
            result = {"number": hex(number), "hash": "0x" + f"{number:064x}"}
        elif method == "eth_getCode":
            number = int(params[1], 16)
            result = "0x6000" if number >= deployment_block else "0x"
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    return httpx.MockTransport(respond)


@pytest.mark.asyncio
async def test_collection_probe_verifies_mainnet_code_and_exact_deployment() -> None:
    provider = JsonRpcEvmProvider(
        endpoint="https://credential.invalid/rpc", transport=rpc_transport()
    )
    probe = await EthereumCollectionDiscovery(provider).probe(ADDRESS)
    assert probe.normalized_address == ADDRESS
    assert probe.deployment_block_number == 7
    assert probe.deployment_block_hash == "0x" + f"{7:064x}"
    assert probe.deployment_confidence is DeploymentConfidence.EXACT
    assert probe.deployment_confidence_value == 100


@pytest.mark.asyncio
async def test_collection_probe_rejects_wrong_chain_and_non_contract() -> None:
    wrong_chain = JsonRpcEvmProvider(
        endpoint="https://credential.invalid/rpc", transport=rpc_transport(chain_id=2)
    )
    with pytest.raises(RuntimeError, match="chain mismatch"):
        await EthereumCollectionDiscovery(wrong_chain).probe(ADDRESS)

    no_code = JsonRpcEvmProvider(
        endpoint="https://credential.invalid/rpc", transport=rpc_transport(deployment_block=21)
    )
    with pytest.raises(InvalidCollection, match="no contract code"):
        await EthereumCollectionDiscovery(no_code).probe(ADDRESS)


@pytest.mark.asyncio
async def test_provider_classifies_log_range_errors_without_leaking_endpoint() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32005, "message": "query returned too many results"},
            },
        )

    provider = JsonRpcEvmProvider(
        endpoint="https://secret-token.invalid/rpc", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ProviderError) as captured:
        await provider.logs(address=ADDRESS, start_block=1, end_block=5000)
    assert captured.value.transient
    assert captured.value.split_range
    assert "secret-token" not in str(captured.value)


@pytest.mark.asyncio
async def test_provider_classifies_log_http_403_as_a_splittable_range() -> None:
    provider = JsonRpcEvmProvider(
        endpoint="https://secret-token.invalid/rpc",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request)),
    )
    with pytest.raises(ProviderError) as captured:
        await provider.logs(address=ADDRESS, start_block=1, end_block=50)
    assert captured.value.transient
    assert captured.value.split_range
    assert captured.value.code == "http_403"
    assert "secret-token" not in str(captured.value)


@pytest.mark.asyncio
async def test_provider_normalizes_transaction_receipt_and_trace_evidence() -> None:
    tx_hash = "0x" + "aa" * 32

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        results: dict[str, object] = {
            "eth_getTransactionByHash": {
                "hash": tx_hash,
                "from": ADDRESS,
                "to": "0x" + "22" * 20,
                "value": "0x10",
                "input": "0x12345678",
                "blockNumber": "0x20",
            },
            "eth_getTransactionReceipt": {
                "transactionHash": tx_hash,
                "blockNumber": "0x20",
                "blockHash": "0x" + "33" * 32,
                "status": "0x1",
                "gasUsed": "0x5208",
                "effectiveGasPrice": "0x3b9aca00",
            },
            "debug_traceTransaction": {"type": "CALL", "from": ADDRESS},
            "eth_getStorageAt": "0x" + "00" * 12 + "44" * 20,
        }
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": results[body["method"]]},
        )

    provider = JsonRpcEvmProvider(
        endpoint="https://credential.invalid/rpc", transport=httpx.MockTransport(respond)
    )
    transaction = await provider.transaction(tx_hash)
    receipt = await provider.receipt(tx_hash)
    trace = await provider.trace_transaction(tx_hash)
    storage = await provider.storage_at(ADDRESS, "0x" + "00" * 32, 32)
    assert transaction.value_wei == 16
    assert transaction.block_number == 32
    assert receipt.status == 1
    assert receipt.gas_used == 21_000
    assert trace["type"] == "CALL"
    assert storage == bytes.fromhex("00" * 12 + "44" * 20)
