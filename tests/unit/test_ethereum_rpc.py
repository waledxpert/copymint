import httpx
import pytest

from app.infrastructure.ethereum_rpc import ChainstackEthereumBalanceClient


@pytest.mark.asyncio
async def test_balance_is_read_at_a_pinned_mainnet_block() -> None:
    calls: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        calls.append(body)
        results = {
            "eth_chainId": "0x1",
            "eth_blockNumber": "0x10",
            "eth_getBalance": "0xde0b6b3a7640000",
        }
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": results[body["method"]]}
        )

    client = ChainstackEthereumBalanceClient(
        endpoint="https://example.invalid/rpc", transport=httpx.MockTransport(respond)
    )
    balance, block = await client.balance_at_latest_block(
        address="0x1111111111111111111111111111111111111111"
    )
    assert (balance, block) == (10**18, 16)
    assert calls[-1]["params"][-1] == "0x10"  # type: ignore[index]


@pytest.mark.asyncio
async def test_balance_client_rejects_wrong_chain() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0x2"})
    )
    client = ChainstackEthereumBalanceClient(
        endpoint="https://example.invalid/rpc", transport=transport
    )
    with pytest.raises(RuntimeError, match="chain ID"):
        await client.balance_at_latest_block(address="0x1111111111111111111111111111111111111111")
