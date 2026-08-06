"""Provider-independent Ethereum read contract."""

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, transient: bool, split_range: bool = False) -> None:
        super().__init__(f"Ethereum provider request failed ({code})")
        self.code = code
        self.transient = transient
        self.split_range = split_range


@dataclass(frozen=True, slots=True)
class BlockReference:
    number: int
    block_hash: str


@dataclass(frozen=True, slots=True)
class EvmLog:
    address: str
    topics: tuple[str, ...]
    data: str
    block_number: int
    block_hash: str
    transaction_hash: str
    log_index: int
    removed: bool


@dataclass(frozen=True, slots=True)
class EvmTransaction:
    transaction_hash: str
    sender: str
    recipient: str | None
    value_wei: int
    input_data: str
    block_number: int


@dataclass(frozen=True, slots=True)
class EvmReceipt:
    transaction_hash: str
    block_number: int
    block_hash: str
    status: int
    gas_used: int
    effective_gas_price: int | None


class EvmProvider(Protocol):
    async def chain_id(self) -> int: ...

    async def block(self, tag: int | str) -> BlockReference: ...

    async def code(self, address: str, block: int | str = "latest") -> bytes: ...

    async def storage_at(self, address: str, slot: str, block: int | str) -> bytes: ...

    async def logs(
        self,
        *,
        address: str,
        start_block: int,
        end_block: int,
        topics: tuple[str | None, ...] = (),
    ) -> list[EvmLog]: ...

    async def transaction(self, transaction_hash: str) -> EvmTransaction: ...

    async def receipt(self, transaction_hash: str) -> EvmReceipt: ...

    async def trace_transaction(self, transaction_hash: str) -> dict[str, object]: ...
