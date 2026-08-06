import pytest

from app.application.ethereum.ports import BlockReference, EvmLog, EvmReceipt, EvmTransaction
from app.application.ethereum.proxies import (
    EIP1967_IMPLEMENTATION_SLOT,
    UPGRADED_TOPIC,
    Eip1967ImplementationResolver,
    InvalidProxyEvidence,
)

PROXY = "0x" + "11" * 20
IMPLEMENTATION_A = "0x" + "22" * 20
IMPLEMENTATION_B = "0x" + "33" * 20


def storage_word(address: str | None) -> bytes:
    if address is None:
        return bytes(32)
    return bytes.fromhex("00" * 12 + address.removeprefix("0x"))


def address_topic(address: str) -> str:
    return "0x" + "00" * 12 + address.removeprefix("0x")


class ProxyProvider:
    def __init__(self, *, final_override: str | None = IMPLEMENTATION_B) -> None:
        self.final_override = final_override

    async def chain_id(self) -> int:
        return 1

    async def block(self, tag: int | str) -> BlockReference:
        assert isinstance(tag, int)
        return BlockReference(tag, "0x" + f"{tag:064x}")

    async def code(self, address: str, block: int | str = "latest") -> bytes:
        return b"\x60\x00" if address.lower() in {IMPLEMENTATION_A, IMPLEMENTATION_B} else b""

    async def storage_at(self, address: str, slot: str, block: int | str) -> bytes:
        assert address.lower() == PROXY
        assert slot == EIP1967_IMPLEMENTATION_SLOT
        assert isinstance(block, int)
        if block == 20:
            return storage_word(self.final_override)
        return storage_word(IMPLEMENTATION_A if block < 15 else IMPLEMENTATION_B)

    async def logs(
        self,
        *,
        address: str,
        start_block: int,
        end_block: int,
        topics: tuple[str | None, ...] = (),
    ) -> list[EvmLog]:
        assert address.lower() == PROXY
        assert topics == (UPGRADED_TOPIC,)
        if not start_block <= 15 <= end_block:
            return []
        return [
            EvmLog(
                address=PROXY,
                topics=(UPGRADED_TOPIC, address_topic(IMPLEMENTATION_B)),
                data="0x",
                block_number=15,
                block_hash="0x" + "44" * 32,
                transaction_hash="0x" + "55" * 32,
                log_index=3,
                removed=False,
            )
        ]

    async def transaction(self, transaction_hash: str) -> EvmTransaction:
        raise NotImplementedError

    async def receipt(self, transaction_hash: str) -> EvmReceipt:
        raise NotImplementedError

    async def trace_transaction(self, transaction_hash: str) -> dict[str, object]:
        raise NotImplementedError


async def test_eip1967_history_builds_verified_non_overlapping_intervals() -> None:
    resolver = Eip1967ImplementationResolver(ProxyProvider(), initial_chunk=20, maximum_chunk=20)
    history = await resolver.history(PROXY, start_block=10, end_block=20)
    assert [
        (item.implementation_address.lower(), item.effective_from_block, item.effective_to_block)
        for item in history
    ] == [
        (IMPLEMENTATION_A, 10, 14),
        (IMPLEMENTATION_B, 15, None),
    ]
    assert history[1].evidence["kind"] == "eip1967_upgraded_event"


async def test_eip1967_history_rejects_event_and_final_storage_disagreement() -> None:
    resolver = Eip1967ImplementationResolver(
        ProxyProvider(final_override=IMPLEMENTATION_A), initial_chunk=20, maximum_chunk=20
    )
    with pytest.raises(InvalidProxyEvidence, match="does not match"):
        await resolver.history(PROXY, start_block=10, end_block=20)


async def test_eip1967_non_proxy_remains_unknown() -> None:
    resolver = Eip1967ImplementationResolver(
        ProxyProvider(final_override=None), initial_chunk=20, maximum_chunk=20
    )
    assert await resolver.implementation_at(PROXY, 20) is None
