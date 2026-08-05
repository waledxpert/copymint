# ADR-006: Paper simulation and evidence levels

- Status: Accepted
- Date: 2026-08-05
- Owners: Blockchain engineering, security, product owner

## Context

Release 1 prepares paper copy-mint plans but does not sign or broadcast. A successful `eth_call` alone does not prove that the expected NFT will be minted, that every internal call is acceptable, or that state will remain unchanged until a real transaction. Chainstack offers standard calls and debug trace methods when the selected node plan enables them.

Users need an accurate explanation of what was checked and what remains uncertain.

## Decision

Paper planning uses a freshly constructed transaction for one workspace-owned execution-wallet address. It never reuses source calldata, proofs, signatures, nonces, vouchers, or recipient-bound values.

The planner runs, in order:

1. verify chain ID, adapter version, collection, and execution-wallet ownership;
2. re-read sale state, phase, supply, price, wallet limit, payment asset, and time window;
3. independently check the execution wallet's eligibility;
4. construct typed unsigned transaction data;
5. calculate native/token value in integer base units;
6. run `eth_estimateGas`;
7. run `eth_call` at a recorded block tag/hash;
8. run `debug_traceCall` with supported built-in tracers when available;
9. inspect destinations, values, internal calls, failure reasons, and available state-diff/effect evidence;
10. enforce the Release 1 paper policy;
11. persist the exact input hash, block reference, results, adapter version, evidence level, warnings, and expiry.

Simulation levels:

| Level | Meaning | User-facing decision |
|---|---|---|
| `verified` | Call and gas estimation succeed; trace/effect evidence matches the adapter's expected contract interactions and no forbidden interaction appears. | `paper_ready`, still explicitly not a guarantee. |
| `partial` | Call and gas estimation succeed, but trace/effect evidence is incomplete while route and eligibility are otherwise recognized. | Paper report with prominent limitations; never manual/auto ready. |
| `inconclusive` | Required method unavailable, evidence conflicts, expected effects cannot be supported, or provider state is inconsistent. | Blocked/inconclusive; do not describe as successful. |
| `failed` | Revert, sold out, ineligible, price/policy violation, forbidden approval/call, or malformed result. | Not copyable or expired with reason code. |

`debug_traceCall` capability is probed in staging. The implementation may use `callTracer` for the internal call tree and `prestateTracer` diff mode where supported. If the purchased node cannot provide the evidence required by an adapter, that adapter cannot produce `verified` plans.

Pinned historical fork tests provide stronger deterministic adapter verification. They are release tests, not a substitute for re-reading current production state.

Every Telegram paper result begins with `PAPER ONLY — NOTHING WAS SIGNED OR SENT` and shows chain, wallet address, collection, route, quantity, current price, gas estimate, worst-case total, evidence level, block reference, expiry, and warnings.

## Safety rules

- Only allowlisted adapter name/version pairs can reach the planner.
- Destination and every material internal call are compared with adapter expectations.
- Unexpected ERC-20/NFT approvals fail unless the adapter and policy explicitly allow an exact approval.
- Unknown delegate calls, value transfers, recipient changes, or wallet-bound eligibility fail closed.
- A changed price or sale state creates a new plan version; it does not mutate an existing plan.
- Plans are immutable and short-lived.
- Release 1 has no signer/broadcast transition from a paper plan.

## Consequences

- Paper reports communicate uncertainty rather than offering false certainty.
- Debug/trace plan capability directly affects whether plans can be `verified`.
- More provider calls are required per plan.
- Adapters need explicit expected-call/effect specifications and negative fixtures.
- A later manual release must re-quote and re-simulate immediately before signing.

## Rejected alternatives

- Treating `eth_estimateGas` success as safe: rejected because it is not an interaction-policy check.
- Treating `eth_call` success as proof of mint: rejected because return success alone does not prove expected effects.
- Replaying observed calldata: rejected because it may contain wallet-bound or stale values.
- Reporting every provider limitation as success with a warning: rejected because some missing evidence is release-blocking.
- Fork-only production decisions: rejected because pinned fork state is not current sale state.

## Verification

- Direct and SeaDrop positive fixtures reach the intended evidence level.
- Allowlist, signed, gated, sold-out, price-change, unexpected approval, and unknown-call fixtures fail.
- Removing trace capability downgrades or blocks according to adapter requirements.
- Stored hashes reproduce the exact paper transaction and evidence input.
- No Release 1 endpoint or task can advance a paper plan to signed/broadcast.

## References

- https://docs.chainstack.com/reference/ethereum-tracecall
- https://docs.chainstack.com/reference/ethereum-debug-trace-rpc-methods
