"""Conservative EIP-1967 implementation-history discovery."""

from dataclasses import dataclass

from web3 import Web3

from app.application.ethereum.ports import EvmLog, EvmProvider
from app.application.ethereum.scanner import AdaptiveHistoricalScanner, ScanBatch

EIP1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
UPGRADED_TOPIC = Web3.keccak(text="Upgraded(address)").hex()


class InvalidProxyEvidence(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImplementationInterval:
    implementation_address: str
    effective_from_block: int
    effective_to_block: int | None
    evidence: dict[str, object]


class _LogCollector:
    def __init__(self) -> None:
        self.logs: list[EvmLog] = []

    async def commit(self, batch: ScanBatch) -> None:
        self.logs.extend(batch.logs)


def implementation_from_word(value: bytes) -> str | None:
    if len(value) != 32:
        raise InvalidProxyEvidence("EIP-1967 storage word must contain 32 bytes")
    if not any(value):
        return None
    if any(value[:12]):
        raise InvalidProxyEvidence("EIP-1967 implementation word is not an address")
    return Web3.to_checksum_address("0x" + value[-20:].hex())


def implementation_from_upgrade(log: EvmLog) -> str:
    if len(log.topics) != 2 or log.topics[0].lower() != UPGRADED_TOPIC:
        raise InvalidProxyEvidence("Upgraded event topics are malformed")
    try:
        value = bytes.fromhex(log.topics[1].removeprefix("0x"))
    except ValueError:
        raise InvalidProxyEvidence("Upgraded implementation topic is malformed") from None
    implementation = implementation_from_word(value)
    if implementation is None:
        raise InvalidProxyEvidence("Upgraded implementation cannot be the zero address")
    return implementation


class Eip1967ImplementationResolver:
    def __init__(
        self,
        provider: EvmProvider,
        *,
        initial_chunk: int = 100,
        maximum_chunk: int = 5000,
    ) -> None:
        self._provider = provider
        self._scanner = AdaptiveHistoricalScanner(
            provider,
            initial_chunk=initial_chunk,
            maximum_chunk=maximum_chunk,
        )

    async def implementation_at(self, address: str, block: int) -> str | None:
        if block < 0:
            raise ValueError("implementation block cannot be negative")
        word = await self._provider.storage_at(address, EIP1967_IMPLEMENTATION_SLOT, block)
        return implementation_from_word(word)

    async def history(
        self,
        address: str,
        *,
        start_block: int,
        end_block: int,
    ) -> tuple[ImplementationInterval, ...]:
        if start_block < 0 or end_block < start_block:
            raise ValueError("invalid proxy history range")
        checksum = Web3.to_checksum_address(address)
        collector = _LogCollector()
        await self._scanner.scan(
            address=checksum,
            start_block=start_block,
            end_block=end_block,
            consumer=collector,
            topics=(UPGRADED_TOPIC,),
        )
        ordered = sorted(collector.logs, key=lambda item: (item.block_number, item.log_index))
        upgrades: dict[int, tuple[str, EvmLog]] = {}
        for log in ordered:
            implementation = implementation_from_upgrade(log)
            if not await self._provider.code(implementation, log.block_number):
                raise InvalidProxyEvidence("Upgraded implementation has no contract code")
            upgrades[log.block_number] = (implementation, log)

        baseline_block = start_block - 1 if start_block > 0 else start_block
        baseline = await self.implementation_at(checksum, baseline_block)
        intervals: list[ImplementationInterval] = []
        active_address = baseline
        active_from = start_block
        active_evidence: dict[str, object] = {
            "kind": "eip1967_storage",
            "observed_at_block": baseline_block,
        }
        for block_number, (implementation, log) in sorted(upgrades.items()):
            if active_address is not None and active_address.lower() != implementation.lower():
                intervals.append(
                    ImplementationInterval(
                        active_address,
                        active_from,
                        block_number - 1,
                        active_evidence,
                    )
                )
            if active_address is None or active_address.lower() != implementation.lower():
                active_address = implementation
                active_from = block_number
                active_evidence = {
                    "kind": "eip1967_upgraded_event",
                    "block_hash": log.block_hash,
                    "transaction_hash": log.transaction_hash,
                    "log_index": log.log_index,
                }
        final_implementation = await self.implementation_at(checksum, end_block)
        if final_implementation is None:
            if active_address is not None:
                raise InvalidProxyEvidence("implementation disappeared without upgrade evidence")
            return ()
        if active_address is None or active_address.lower() != final_implementation.lower():
            raise InvalidProxyEvidence("implementation history does not match finalized storage")
        intervals.append(ImplementationInterval(active_address, active_from, None, active_evidence))
        return tuple(intervals)
