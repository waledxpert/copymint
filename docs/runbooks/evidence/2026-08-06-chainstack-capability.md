# Chainstack Development Capability Probe — 2026-08-06

- Environment: development
- Provider alias: `chainstack-primary`
- Ethereum chain ID: 1 — passed
- `safe` block tag: passed
- `finalized` block tag: passed
- Finality ordering (`safe >= finalized`): passed
- Historical `eth_getCode` at the finalized boundary: passed
- WSS `eth_subscribe` / `eth_unsubscribe` for `newHeads`: passed
- Endpoint redaction: passed; no HTTPS or WSS credential was recorded
- Effective `eth_getLogs` range behavior: one-block and 10-block requests passed; 50-block,
  99-block, 100-block, and 1,001-block requests returned HTTP 403. This is stricter than the
  currently documented 100-block Developer-plan range and must be handled adaptively.
- Transaction lookup: passed using finalized WETH transfer evidence.
- Receipt lookup and block consistency: passed.
- `debug_traceTransaction` with `callTracer`: unavailable; HTTP 403.

Observed during the probe:

- Safe block: `25692031`
- Finalized block: `25691999`

This verifies the baseline provider contract, bounded log access, and transaction/receipt access.
The scanner classifies an HTTP 403 from `eth_getLogs` as a splittable range response and continues
shrinking until the endpoint accepts the request. Debug/trace remains a blocking provider capability
for trace-dependent identity and paper-simulation evidence. Archive-depth behavior and large/dense
log retrieval remain separate capability gates.
