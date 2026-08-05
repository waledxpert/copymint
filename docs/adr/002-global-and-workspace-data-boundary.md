# ADR-002: Global intelligence and workspace-private data

- Status: Accepted
- Date: 2026-08-05
- Owners: Product owner, backend engineering, security

## Context

CopyMint is used by multiple unrelated people. Ethereum observations are public and expensive to reconstruct, while watchlists, strategies, execution wallets, opportunities, and usage history are private user data. Duplicating collection scans per user wastes provider capacity; sharing every table leaks private activity.

## Decision

Use one shared global intelligence plane and a workspace-private control plane.

Every approved Telegram user receives one personal workspace and a `workspace_owner` membership. The workspace abstraction is used from the first migration so team workspaces can be added later without redesigning private tables.

Global tables include:

- chains and canonical block metadata;
- collections and proxy implementation intervals;
- scan jobs and checkpoints;
- normalized transactions, receipts, traces, and evidence references;
- immutable mint events;
- factual wallet-to-collection aggregates;
- versioned classifiers, scores, and adapter metadata.

Workspace-private tables include:

- memberships and notification destinations;
- collection subscriptions;
- tracked wallets and notes;
- strategies and limits;
- opportunities and paper plans;
- execution wallets and signer references;
- callback challenges and workspace audit events.

The server derives workspace context from the authenticated numeric Telegram user ID. A message, callback, job payload, or API client may reference a private resource ID, but may not authoritatively choose its workspace.

Private repository methods require `workspace_id`. Private unique constraints include `workspace_id` where the resource is not globally unique. Background jobs carry a workspace ID, correlation ID, idempotency key, and the immutable source resource ID.

PostgreSQL row-level security is used as defense in depth on workspace-private tables. Application and worker roles set a transaction-local workspace context before private queries. Administrative/migration roles are separate and unavailable to normal services.

Global on-chain data is not anonymous user data. Query access still requires an approved user, and product responses do not reveal another workspace's subscriptions, watch reasons, opportunities, or wallet inventory.

## Data lifecycle

- Revocation blocks access and new private jobs; it does not delete audit evidence or on-chain facts.
- Removing a watchlist entry deactivates it and preserves history.
- Reclassification writes a new derivation/version; raw evidence is not overwritten.
- User export/deletion requirements will distinguish public chain evidence from private workspace records.

## Consequences

- A collection is scanned once and reused by every approved workspace.
- Private intent and custody data remain isolated.
- Every service and test must carry explicit workspace context.
- Some analytics are global facts but their use in recommendations is workspace-specific.
- Future team workspaces are possible without changing resource ownership keys.

## Rejected alternatives

- One database/schema per user: rejected for operational cost and duplicated chain data.
- One global allowlist and unscoped product tables: rejected because unrelated users would share private state.
- Relying only on Telegram handler checks: rejected because workers and internal APIs could bypass them.
- Treating wallet addresses as secret: rejected as impossible on a public chain; the private information is ownership, grouping, labels, intent, and platform activity.

## Verification

- Isolation tests create two workspaces and attempt every private read/mutation across them.
- Direct repository calls without workspace context fail.
- RLS tests use the same IDs under different transaction contexts.
- Queue jobs cannot load a resource belonging to a different workspace.
- Cross-workspace attempts return not found and create a security audit event without leaking the resource owner.
