# ADR-001: Ethereum and Chainstack provider contract

- Status: Accepted
- Date: 2026-08-05
- Owners: Product owner, blockchain engineering

## Context

CopyMint launches on one EVM chain. Historical NFT scanning, identity enrichment, live monitoring, finality handling, and paper simulation all depend on provider behavior. Direct provider calls throughout the application would make retry behavior, evidence quality, and later failover inconsistent.

## Decision

Ethereum mainnet is the only production chain in Release 1. Its immutable numeric identity is `chain_id = 1`.

Chainstack is the primary provider. The application depends on an internal `EvmProvider` interface rather than Chainstack-specific response objects. Development, staging, and production use separate HTTPS and WSS credentials.

The provider interface owns:

- `eth_chainId` startup verification;
- block number/hash retrieval;
- `safe` and `finalized` block resolution;
- bounded `eth_getLogs` queries;
- transaction and receipt retrieval;
- contract code and read-only calls;
- gas estimation;
- trace capability probing and supported trace calls;
- WebSocket new-head notifications;
- explicit error classification, deadlines, retry hints and metrics.

WebSocket events are notifications, not durable truth. The live worker persists a block cursor and fetches canonical blocks through HTTPS. Reconnect always performs cursor-based catch-up.

Historical scans use adaptive chunks. They start at 2,000 blocks, never exceed 5,000 blocks, and shrink for dense collections, timeouts, suspicious response size, or provider errors. These are configuration bounds, not assumptions that every 5,000-block query succeeds.

Historical collection scans stop at a fixed finalized boundary. Live observations begin provisional and are promoted to safe/finalized. A configurable 64-block initial reorg lookback is retained until production evidence justifies a different value.

All RPC URLs are secrets because Chainstack credentials are embedded in the endpoint. Logs may contain only provider aliases and RPC method names.

Production must have a tested secondary Ethereum RPC provider before real transaction execution is released. Release 1 may launch with Chainstack alone if outages pause new paper planning and durable scanners resume cleanly.

## Provider capability gate

The purchased node/plan is probed in staging for:

- Ethereum chain ID 1;
- `eth_getLogs` behavior over low- and high-density ranges;
- `safe` and `finalized` tags;
- WSS new heads and reconnect behavior;
- `debug_traceTransaction` and `debug_traceCall` with supported built-in tracers;
- archive-state access needed by selected historical fixtures.

Unavailable capabilities lower evidence quality or block dependent functionality. They are never silently emulated with guesses.

## Consequences

- Chainstack can be replaced or supplemented without changing domain services.
- Live ingestion tolerates WebSocket gaps.
- Backfills trade some speed for predictable provider behavior.
- Debug/trace and archive access may require a paid Chainstack plan.
- Ethereum-only assumptions remain inside the EVM/chain configuration boundary.

## Rejected alternatives

- Calling web3.py directly from bot handlers: rejected because it couples user interaction to provider behavior.
- Treating WebSocket delivery as complete: rejected because disconnects can lose notifications.
- Scanning from genesis in one request: rejected because `eth_getLogs` cost and response size are unbounded.
- Automatically searching other chains for a supplied address: rejected because it can produce incorrect collection identity.

## Verification

- Provider contract tests cover every supported RPC method and error class.
- Startup fails if `eth_chainId != 1`.
- Cursor catch-up tests drop WebSocket notifications intentionally.
- Fixture scans kill the worker mid-range and confirm idempotent resume.
- Logs are tested not to contain the configured RPC URLs.

## References

- https://docs.chainstack.com/reference/ethereum-getlogs
- https://docs.chainstack.com/docs/protocols-modes-and-types
- https://docs.chainstack.com/reference/ethereum-debug-trace-rpc-methods
- https://docs.chainstack.com/reference/ethereum-tracecall
