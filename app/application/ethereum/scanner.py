"""Adaptive, resumable historical log-range scanner."""

from dataclasses import dataclass
from typing import Protocol

from app.application.ethereum.ports import EvmLog, EvmProvider, ProviderError


@dataclass(frozen=True, slots=True)
class ScanBatch:
    start_block: int
    end_block: int
    end_block_hash: str
    logs: tuple[EvmLog, ...]


class ScanBatchConsumer(Protocol):
    async def commit(self, batch: ScanBatch) -> None: ...


class AdaptiveHistoricalScanner:
    def __init__(
        self,
        provider: EvmProvider,
        *,
        initial_chunk: int = 2000,
        maximum_chunk: int = 5000,
        dense_log_threshold: int = 5000,
    ) -> None:
        if not 1 <= initial_chunk <= maximum_chunk:
            raise ValueError("initial chunk must be between one and the maximum chunk")
        self._provider = provider
        self._initial_chunk = initial_chunk
        self._maximum_chunk = maximum_chunk
        self._dense_log_threshold = dense_log_threshold

    async def scan(
        self,
        *,
        address: str,
        start_block: int,
        end_block: int,
        consumer: ScanBatchConsumer,
        topics: tuple[str | None, ...] = (),
    ) -> None:
        if start_block < 0 or end_block < start_block:
            raise ValueError("invalid scan range")
        cursor = start_block
        chunk = self._initial_chunk
        while cursor <= end_block:
            batch_end = min(cursor + chunk - 1, end_block)
            try:
                logs = await self._provider.logs(
                    address=address,
                    start_block=cursor,
                    end_block=batch_end,
                    topics=topics,
                )
            except ProviderError as exc:
                if not exc.split_range or chunk == 1:
                    raise
                chunk = max(1, chunk // 2)
                continue
            boundary = await self._provider.block(batch_end)
            if boundary.number != batch_end:
                raise ProviderError("block_boundary_mismatch", transient=True)
            await consumer.commit(ScanBatch(cursor, batch_end, boundary.block_hash, tuple(logs)))
            cursor = batch_end + 1
            if len(logs) >= self._dense_log_threshold:
                chunk = max(1, chunk // 2)
            elif len(logs) < max(1, self._dense_log_threshold // 4):
                chunk = min(self._maximum_chunk, max(chunk + 1, chunk * 2))
