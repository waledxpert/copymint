from app.application.ethereum.ports import BlockReference, EvmLog, ProviderError
from app.application.ethereum.scanner import AdaptiveHistoricalScanner, ScanBatch


class RangeLimitedProvider:
    def __init__(self) -> None:
        self.attempts: list[tuple[int, int]] = []

    async def chain_id(self) -> int:
        return 1

    async def block(self, tag: int | str) -> BlockReference:
        assert isinstance(tag, int)
        return BlockReference(tag, "0x" + f"{tag:064x}")

    async def code(self, address: str, block: int | str = "latest") -> bytes:
        raise NotImplementedError

    async def logs(
        self,
        *,
        address: str,
        start_block: int,
        end_block: int,
        topics: tuple[str | None, ...] = (),
    ) -> list[EvmLog]:
        self.attempts.append((start_block, end_block))
        if end_block - start_block + 1 > 3:
            raise ProviderError("rpc_-32005", transient=True, split_range=True)
        return []


class RecordingConsumer:
    def __init__(self) -> None:
        self.batches: list[ScanBatch] = []

    async def commit(self, batch: ScanBatch) -> None:
        self.batches.append(batch)


async def test_scanner_shrinks_ranges_and_commits_without_gaps() -> None:
    provider = RangeLimitedProvider()
    consumer = RecordingConsumer()
    scanner = AdaptiveHistoricalScanner(
        provider, initial_chunk=8, maximum_chunk=8, dense_log_threshold=100
    )
    await scanner.scan(
        address="0x" + "11" * 20,
        start_block=10,
        end_block=18,
        consumer=consumer,
    )
    assert provider.attempts[:3] == [(10, 17), (10, 13), (10, 11)]
    covered = [
        block
        for batch in consumer.batches
        for block in range(batch.start_block, batch.end_block + 1)
    ]
    assert covered == list(range(10, 19))
