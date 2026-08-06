# CopyMint Implementation Plan

> Status: Approved planning baseline
> Last updated: 2026-08-05
> Source specification: `NFT_Mint_Intelligence_Copy_Mint_Technical_Specification.docx`
> Initial network: Ethereum mainnet (`chain_id = 1`)
> Product access: Free, invite/owner-approval only
> First release ceiling: Paper mode; no signing or broadcasting

## 1. Purpose

This file is the working implementation source of truth for CopyMint. It converts the technical specification and owner decisions into an ordered, testable delivery plan.

Use this document to:

- decide what is in and out of each release;
- prevent unsafe work from being enabled too early;
- track implementation tasks and acceptance gates;
- preserve multi-user isolation from the first migration;
- make every blockchain, wallet, Telegram, and deployment decision explicit.

No phase advances merely because its code exists. Its automated tests, operational checks, and exit criteria must pass.

## 2. Locked product decisions

| Decision | Locked position |
|---|---|
| Access model | A person starts the Telegram bot and submits an access request. The platform owner approves or rejects the request. |
| Audience | Multiple unrelated invited users, not only the developer or one trusted team. |
| Pricing | Free during the invite-only release. No billing system in v1. |
| Chain | Ethereum mainnet first. Network identity is always the numeric chain ID, not a display name. |
| RPC provider | Chainstack HTTPS and WebSocket Ethereum endpoints. |
| Hosting | Render. |
| User isolation | Every approved user receives a private personal workspace. Other users cannot see their wallets, strategies, watchlists, opportunities, or audit history. |
| Wallet model | CopyMint creates execution wallets inside an isolated signer. The application stores only public addresses and opaque signer key references. |
| First release | Historical intelligence, overlap analytics, live alerts, execution-wallet creation, and paper mode. |
| Real transactions | Explicitly excluded from the first release. Manual execution is a later gated release. |
| Initial adapters | Direct public contract mints and OpenSea SeaDrop public mints. |
| Default quantity | One NFT. |
| Default execution mode | `alert`, upgradeable per workspace to `paper`; never `manual` or `auto` in v1. |

## 3. Release boundaries

### 3.1 Release 1 — Invite-only intelligence and paper mode

Release 1 includes:

- Telegram access request, approval, rejection, revocation, and private-chat authorization;
- one private personal workspace per approved user;
- signer-created Ethereum execution wallets, subject to a configurable per-user limit;
- wallet address, balance, and signer-health display without exposing key material;
- Ethereum collection registration and historical mint scanning;
- ERC-721, ERC-1155, and ERC-2309 mint detection;
- recipient, transaction sender, operator, payer, and probable initiator resolution;
- exact overlap, at-least-k overlap, and wallet support counts;
- private watchlists and live mint alerts;
- direct-public and SeaDrop-public route recognition;
- eligibility, quote, transaction building, gas estimation, and simulation;
- paper execution plans and explicit rejection reasons;
- audit logs, metrics, backups, provider health, and operational runbooks.

Release 1 does not include:

- signing or broadcasting transactions;
- real-fund approvals from Telegram;
- automatic minting;
- reuse of another wallet's proof, signature, voucher, nonce, or calldata;
- allowlist bypassing, token-gate bypassing, CAPTCHAs, or platform-protection bypassing;
- multiple EVM chains;
- arbitrary launchpad adapters;
- marketplace purchases;
- secondary-market trading;
- wallet private-key delivery through Telegram;
- billing, subscriptions, or public self-service registration.

### 3.2 Release 2 — Restricted manual execution

Release 2 may begin only after Release 1 has stable production history and a separate security review. It will add signer authorization policies, immutable approvals, atomic spend commitments, nonce management, broadcasting, and receipt reconciliation.

### 3.3 Release 3 — Guarded automation

Unattended spending is a separate product release. It requires short-lived authority, independent signer caps, incident drills, sustained manual-operation history, and an external security review.

## 4. Non-negotiable engineering rules

1. Telegram is a control plane, never a key vault.
2. Private keys and seed phrases never appear in Telegram, application logs, PostgreSQL rows, error trackers, or normal application configuration.
3. Every private query and mutation is scoped by a server-derived `workspace_id`.
4. A callback never supplies authoritative user, workspace, chain, wallet, route, price, or policy values.
5. On-chain observations are immutable and globally reusable; user intent and user-owned resources are private.
6. Checkpoints advance atomically with all decoded events for the completed block range.
7. Every externally retried action is idempotent.
8. Unknown or conflicting evidence is preserved as unknown; the system does not fabricate certainty.
9. CopyMint builds fresh transactions from current state. It never replays source calldata blindly.
10. No signing or broadcasting code path is enabled in Release 1.
11. Money and token amounts use integer base units. Floating-point arithmetic is prohibited.
12. Every security-sensitive state transition writes an append-only audit event.
13. Production services use paid persistent infrastructure. Ephemeral local files are not authoritative storage.

## 5. System architecture

```text
Telegram
   |
   | HTTPS webhook + Telegram secret header
   v
Render web service: bot-api
   |-- authorization/application services
   |-- PostgreSQL repositories
   |-- Redis-compatible queue and locks
   |
   +------> indexer worker ------> Chainstack Ethereum HTTPS
   +------> live worker ---------> Chainstack Ethereum WSS/HTTPS
   +------> analytics worker ----> PostgreSQL
   +------> opportunity worker --> adapters + paper planner
   |
   +------> private signer service
               |-- wallet creation
               |-- encrypted key references
               `-- signing endpoint disabled in Release 1

Shared infrastructure:
   PostgreSQL = authoritative durable state
   Render Key Value = queue, locks, rate limits, short-lived challenges
   Metrics/log platform = redacted telemetry and alerts
```

### 5.1 Runtime services

| Service | Render type | Responsibility |
|---|---|---|
| `bot-api` | Web service | Telegram webhook, health endpoints, authorization, application APIs, commands and callbacks. |
| `indexer-worker` | Background worker | Historical scans, receipt enrichment, retry handling, checkpoints and canonicality repair. |
| `live-worker` | Background worker | New-block ingestion, durable cursors, tracked-wallet correlation and reorg lookback. |
| `analytics-worker` | Background worker | Wallet aggregates, overlap materialization, scoring versions and watchlist promotion. |
| `opportunity-worker` | Background worker | Route recognition, eligibility, quote/build/simulate and paper-plan lifecycle. |
| `signer` | Private service | Key creation and encrypted custody. Structured signing remains disabled in Release 1. |
| `postgres` | Render PostgreSQL | Source of truth for all durable state. |
| `queue` | Render Key Value | Job queues, distributed locks, rate limits and expiring challenges. |

Workers must not depend on local disk. Deployments may replace a running instance at any time.

### 5.2 Global versus private data

Global on-chain data is shared to avoid rescanning Ethereum for every user:

- chains and canonical blocks;
- collections and proxy implementation history;
- scan jobs and checkpoints;
- transactions, receipts, traces and normalized evidence;
- mint events;
- global wallet-to-collection statistics;
- adapter versions and protocol metadata.

Workspace-private data includes:

- memberships and access state;
- collection subscriptions;
- tracked wallets and private notes;
- strategies and limits;
- opportunities and paper plans;
- execution wallets and signer references;
- notification preferences;
- approval challenges;
- private audit history.

## 6. Multi-user and access-control model

### 6.1 Identity hierarchy

```text
platform owner
   `-- approves or rejects Telegram access requests

Telegram user
   `-- membership
       `-- personal workspace
           |-- execution wallets
           |-- tracked wallets
           |-- strategy
           |-- opportunities
           `-- audit events
```

Every approved user receives one personal workspace. The workspace abstraction is retained so team workspaces can be added later without rewriting all private tables.

### 6.2 Platform roles

| Role | Permissions |
|---|---|
| `platform_owner` | Approve/reject/revoke users, pause the platform, inspect platform health and administer adapters. |
| `workspace_owner` | Control only their own workspace, collections, watchlists, wallets, strategies and paper plans. |
| `service_worker` | Perform a bounded job using service credentials; cannot grant access or change policy. |
| `signer` | Create keys and later sign only validated typed plans; cannot grant Telegram access. |

The application must not treat a Telegram username as identity. `telegram_user_id` is the immutable external identity key.

### 6.3 Access-request workflow

1. An unknown user sends `/start` in a private chat.
2. The bot stores an idempotent `access_request` using the numeric Telegram user ID.
3. The user receives a `PENDING_APPROVAL` response and cannot use privileged commands.
4. The platform owner receives a card showing request ID, numeric user ID, display metadata, request time, and approve/reject buttons.
5. The callback contains only an opaque, expiring, single-use challenge ID.
6. The server reloads the access request and verifies the platform owner from configuration/database state.
7. Approval creates the platform user, personal workspace, owner membership, default strategy, and audit events in one transaction.
8. Rejection records the reason and optional cooldown. It creates no workspace.
9. Revocation immediately blocks commands and cancels new jobs while preserving audit and on-chain history.
10. Reapproval requires a new explicit owner action.

Required commands:

- `/start`
- `/help`
- `/access_status`
- `/admin_requests`
- `/admin_approve <request_id>` through an inline confirmation
- `/admin_reject <request_id>` through an inline confirmation
- `/admin_revoke <telegram_user_id>` through an inline confirmation
- `/status`

Administrative commands are accepted only from configured platform-owner Telegram IDs in private chats.

### 6.4 Tenant isolation rules

- Middleware resolves the numeric Telegram user ID to an active membership and workspace.
- Handlers receive an immutable `RequestContext`; they do not accept `workspace_id` from messages or callbacks.
- Repository methods that operate on private data require `workspace_id` as a mandatory argument.
- Private-table unique keys include `workspace_id` where appropriate.
- PostgreSQL row-level security should be enabled for private tables where compatible with worker access patterns.
- Service-worker database roles are separated from migration and administrative roles.
- Cross-workspace access attempts return a generic not-found result and emit a security audit event.
- Tests create at least two users and prove that every private endpoint, command, callback, job, and repository is isolated.

## 7. Data model plan

All IDs are UUIDv7 or another monotonic, non-guessable identifier selected once for the repository. Timestamps are UTC. Ethereum addresses are normalized consistently and accompanied by a checksum display form.

### 7.1 Access and workspace tables

| Table | Core fields and constraints |
|---|---|
| `platform_users` | `id`, unique `telegram_user_id`, display metadata, status, approved/revoked timestamps. |
| `access_requests` | `id`, `telegram_user_id`, status, requested/decided timestamps, decided_by, reason; repeated `/start` must not create multiple active requests. |
| `workspaces` | `id`, name, status, created_at; one personal workspace per approved user in v1. |
| `workspace_memberships` | unique `(workspace_id, user_id)`, role, status. |
| `notification_destinations` | workspace-scoped Telegram chat ID, event preferences and enabled state. |
| `callback_challenges` | opaque token hash, action, actor, resource, expiry, consumed timestamp; payload values are not authoritative. |

### 7.2 Global intelligence tables

| Table | Core fields and constraints |
|---|---|
| `chains` | namespace, immutable chain ID, currency and finality configuration. |
| `collections` | unique `(chain_id, normalized_address)`, token standard, deployment boundary and scan status. |
| `collection_implementations` | proxy implementation address and effective block interval. |
| `scan_jobs` | collection, fixed start/end block, status, attempt count and quality warnings. |
| `scan_checkpoints` | unique `(collection_id, scan_version)`, last committed block number/hash. |
| `chain_cursors` | worker purpose, chain ID and last safely processed block/hash. |
| `raw_evidence` | content hash, provider metadata, normalized receipt/trace reference and retention state. |
| `mint_events` | unique `(chain_id, tx_hash, log_index, sub_index)`, all provenance, identities, confidence, route, classification and finality. |
| `wallet_collection_stats` | unique `(chain_id, wallet, collection_id, identity_mode)`, quantities, first/last mint and confidence summary. |
| `wallet_scores` | wallet, immutable score version, score, features and calculated timestamp. |

Do not delete raw mint events when classifications or scores improve. Write versioned derivations and rebuild aggregates.

### 7.3 Workspace-private product tables

| Table | Core fields and constraints |
|---|---|
| `workspace_collections` | unique `(workspace_id, collection_id)`, label, added_by and notification settings. |
| `tracked_wallets` | unique `(workspace_id, chain_id, wallet)`, selection reason, score version and active state. |
| `strategies` | workspace, immutable version, mode, route allowlist, support threshold and paper limits. |
| `execution_wallets` | workspace, chain, public address, opaque `signer_key_id`, label and status; unique chain/address. |
| `opportunities` | workspace, source event, target collection, strategy version, decision, expiry and risk flags. |
| `execution_plans` | workspace, opportunity, wallet, adapter version, quote, unsigned transaction hash, simulation and expiry. |
| `audit_logs` | workspace or platform scope, actor, action, resource, before/after, correlation ID and timestamp. |

Release 2 adds `spend_commitments`, `tx_attempts`, `nonce_reservations`, `approvals`, and `tx_replacements` before any signing is enabled.

### 7.4 Required uniqueness and idempotency keys

- Telegram update: `(bot_id, update_id)`
- Active access request: one active request per `telegram_user_id`
- Collection: `(chain_id, normalized_contract_address)`
- Mint event: `(chain_id, tx_hash, log_index, sub_index)`
- Collection subscription: `(workspace_id, collection_id)`
- Tracked wallet: `(workspace_id, chain_id, normalized_wallet)`
- Opportunity: `(workspace_id, source_mint_event_id, target_collection_id)`
- Paper plan: one current immutable plan version per opportunity and execution wallet
- Wallet-creation challenge: one completed result per idempotency key

## 8. Execution-wallet custody plan

### 8.1 Wallet-creation flow

1. An approved workspace owner sends `/create_wallet` in private chat.
2. The application enforces the configured per-workspace wallet limit.
3. A single-use confirmation displays chain, current wallet count, and the fact that keys will never be sent through Telegram.
4. After confirmation, the application sends a typed, idempotent creation request to the private signer.
5. The signer creates the Ethereum key inside its protected boundary.
6. Key material is envelope-encrypted using a managed KMS/HSM-backed key-encryption key.
7. The signer stores ciphertext and metadata, then returns only the address and opaque `signer_key_id`.
8. The application verifies the returned address and stores the public wallet record.
9. The user receives only the public address and a security warning.

### 8.2 Required signer controls

- The signer is a Render private service with no public URL.
- Signer storage is encrypted and durable; local ephemeral disk is not used as the key database.
- The signer authenticates callers using service credentials and request signatures.
- Every request includes correlation ID, workspace ID, chain ID, action, idempotency key and expiry.
- Key references are namespaced to a workspace and chain.
- The signer refuses cross-workspace references.
- Key plaintext is never returned from an API or written to logs.
- Signing endpoints are compiled/configured off in Release 1.
- A KMS/HSM provider and recovery ceremony must be documented in an ADR before production wallet creation is enabled.
- Production users must see a clear custody/recovery notice before creating or funding a wallet.

### 8.3 Wallet visibility

`/wallets` and `/wallet <id>` query by server-derived workspace. Returning another workspace's wallet ID must behave as not found. Telegram messages show only:

- label;
- shortened and copyable public address;
- Ethereum balance;
- wallet health;
- signer availability;
- whether paper simulation can use the address.

They never show private keys, seed phrases, encrypted blobs, signed raw transactions, signer credentials, or another user's address list.

### 8.4 Recovery release gate

Because users may deposit real assets, production wallet creation is blocked until all of the following exist:

- documented custody terms;
- encrypted backup and restore procedure;
- tested restoration of a non-production key;
- address verification after restore;
- owner-approved user recovery policy;
- incident rotation procedure;
- an out-of-band recovery/export decision that does not use Telegram.

## 9. Ethereum and Chainstack integration

### 9.1 Provider requirements

Provision separate Ethereum mainnet HTTPS and WSS credentials for development, staging, and production. The selected Chainstack plan must support:

- standard Ethereum JSON-RPC;
- `eth_getLogs` historical queries;
- WebSocket new-head or log subscriptions;
- `safe` and `finalized` block tags;
- receipts and transactions;
- debug/trace methods needed by identity resolution and paper simulation;
- sufficient request volume for historical backfills;
- archive access when a selected operation requires historical state.

Debug/trace and archive capability must be verified against the purchased Chainstack plan rather than assumed.

### 9.2 Provider client rules

- Wrap Chainstack behind an internal `EvmProvider` interface.
- Use bounded concurrency, deadlines, exponential backoff with jitter, and explicit error mapping.
- Never log full RPC URLs because they contain credentials.
- Retry only errors classified as transient.
- Cross-check block number and block hash before advancing canonical checkpoints.
- Record method latency, errors and rate-limit responses.
- Keep transaction broadcasting behind a separate interface that is disabled in Release 1.

### 9.3 Historical scanning

- Start Ethereum `eth_getLogs` chunks conservatively and adapt to response size and latency.
- Treat 5,000 blocks as an upper target, not a guaranteed safe range.
- Split ranges on timeout, provider-size errors, suspicious truncation, or excessive log density.
- Scan to a fixed finalized end block.
- Commit decoded events and checkpoint advancement in one PostgreSQL transaction.
- Resume from the durable checkpoint after worker restart.
- Re-read a configurable overlap window to repair reorgs.

### 9.4 Live monitoring

- Use WebSocket new-head subscriptions for low-latency notification.
- Fetch canonical block data over HTTPS so a dropped WebSocket message does not create a permanent gap.
- Persist a durable block cursor.
- On reconnect, catch up every missing block before returning to live mode.
- Initially treat confirmed-block events as provisional and promote them through safe/finalized states.
- Reverse derived statistics and expire dependent opportunities when evidence is reorged.
- Pending/mempool monitoring remains deferred.

## 10. Mint ingestion and identity resolution

### 10.1 Required decoders

- ERC-721 `Transfer` from the zero address.
- ERC-1155 `TransferSingle` from the zero address.
- ERC-1155 `TransferBatch` with deterministic `sub_index` expansion.
- ERC-2309 `ConsecutiveTransfer` with a controlled expansion/storage policy.
- Proxy metadata without changing collection identity from the proxy address.

### 10.2 Enrichment sequence

For each candidate mint transaction:

1. Persist log provenance.
2. Retrieve the transaction and receipt.
3. Decode method selector and known ABI when available.
4. Retrieve trace evidence when required and available.
5. Identify known router/protocol contracts.
6. Store recipient, `tx.from`, operator and payer separately.
7. Resolve probable initiator using versioned reason codes.
8. Classify the mint route and mint type.
9. Store confidence and quality warnings.
10. Update aggregates only from canonical qualifying observations.

### 10.3 Default analytical inclusion

Default support counts use:

- identity mode: `initiator`;
- finality: `safe` or `finalized`;
- classifications: `public_paid_mint` and `public_free_mint`;
- minimum identity confidence: 85;
- distinct collections, not NFT quantity.

Airdrops, admin mints, bridges, migrations, lazy marketplace mints, unresolved relayers, contracts, and spam are excluded by default but remain queryable.

## 11. Analytics plan

Implement factual metrics before subjective scores:

- support count;
- exact pair intersection;
- exact group intersection;
- at-least-k of n overlap;
- Jaccard similarity;
- per-wallet collection history;
- per-collection minter count and scan quality.

Quality scoring is versioned and separate from support count. A score change must never rewrite the underlying events or historical decision provenance.

Required Telegram commands:

- `/add_collection <address>` — Ethereum is implicit in v1 but stored as chain ID 1
- `/scan <collection>`
- `/collections`
- `/overlap`
- `/compare <collection...>`
- `/wallet_history <address>`
- `/watch <address>`
- `/unwatch <address>`

Long results use pagination, compact summaries, and downloadable report generation only if a safe delivery mechanism is implemented.

## 12. Opportunity and paper-mode plan

### 12.1 Opportunity creation

A finalized or sufficiently confirmed mint associated with a tracked wallet creates one workspace-private opportunity. If several private watch reasons match the same source event, aggregate the reasons instead of creating duplicates.

An opportunity records:

- source chain, block, transaction and mint event;
- tracked wallet and reason;
- target collection;
- support count and score version at decision time;
- route, classification, eligibility and confidence;
- observed quantity and source cost evidence;
- adapter name/version;
- risk flags, decision and expiry.

### 12.2 Adapter interface

Each versioned adapter implements:

- `recognize`
- `inspect_sale`
- `check_eligibility`
- `quote`
- `build`
- `simulate`
- `explain_rejection`

Adapters return typed results and reason codes. Unknown contracts or methods remain alert-only.

### 12.3 Initial adapter rules

Direct public mint:

- identify the public function and current sale state;
- replace recipient and quantity correctly;
- use the current price rather than the source transaction's value;
- reject unknown approval requirements or wallet-bound inputs.

SeaDrop public mint:

- recognize supported SeaDrop contracts and public-drop configuration;
- query current price, limits and sale window;
- build fresh data for the user's execution-wallet address;
- reject allowlist proofs, server signatures and token-gated phases unless the user's wallet independently qualifies.

### 12.4 Paper execution sequence

1. Load immutable opportunity and strategy version.
2. Select one workspace-owned Ethereum execution wallet.
3. Re-read sale state, supply, time window, wallet limit, price and payment asset.
4. Check the selected wallet's independent eligibility.
5. Build fresh unsigned transaction data.
6. Calculate native value, token payment, gas estimate and worst-case total.
7. Simulate using verified provider methods.
8. Validate expected contract interactions and state/result evidence.
9. Apply paper limits and risk rules.
10. Persist an immutable paper plan and simulation evidence.
11. Send the user a clear `PAPER ONLY — NOTHING WAS SIGNED OR SENT` result.

If the provider cannot produce enough simulation evidence, mark the plan `simulation_inconclusive`; do not present it as safely executable.

## 13. Telegram experience

### 13.1 Interaction rules

- Privileged commands work only in private chats.
- Unauthorized users may use only `/start`, `/help`, and `/access_status`.
- Every callback is single-use, short-lived, actor-bound and chat-bound.
- Telegram `update_id` is durably deduplicated.
- Messages never expose internal exceptions, RPC credentials, signer references or key data.
- Long-running commands acknowledge immediately and update progress asynchronously.
- Rate limits apply per Telegram user, workspace and command class.

### 13.2 Release 1 command groups

Access:

- `/start`
- `/help`
- `/access_status`

Intelligence:

- `/add_collection`
- `/scan`
- `/collections`
- `/overlap`
- `/compare`
- `/wallet_history`

Monitoring:

- `/watch`
- `/unwatch`
- `/opportunities`

Wallet and paper mode:

- `/create_wallet`
- `/wallets`
- `/paper <opportunity_id>`
- `/strategy`
- `/mode <alert|paper>`

Operations:

- `/status`
- `/pause`

Platform owner:

- `/admin_requests`
- approval/rejection/revocation callbacks
- `/admin_status`
- `/admin_pause`

`/copy`, `/mode manual`, `/mode auto`, and all broadcast operations do not exist or always fail closed in Release 1.

## 14. Repository structure

```text
app/
  bot/
    handlers/
    keyboards/
    middleware/
    messages/
  api/
    routes/
    schemas/
  application/
    access/
    collections/
    analytics/
    wallets/
    opportunities/
  domain/
    entities/
    enums/
    events/
    policies/
    ports/
  chains/
    evm/
      rpc/
      decoders/
      identity/
      finality/
  indexer/
  analytics/
  opportunities/
  execution/
    adapters/
      direct_public/
      seadrop/
    planner/
    simulation/
  signer/
    api/
    custody/
    policy/
  infrastructure/
    db/
      models/
      repositories/
      migrations/
    queue/
    security/
    observability/
  workers/
tests/
  unit/
  database/
  fixtures/
  provider_contract/
  fork/
  telegram/
  isolation/
  end_to_end/
  chaos/
docs/
  adr/
  runbooks/
  threat-model/
render.yaml
Dockerfile
pyproject.toml
```

Handlers call application services. They never call SQLAlchemy repositories or web3 clients directly.

## 15. Technology baseline

- Python with a version pinned in `.python-version` and the container image.
- FastAPI for webhook and internal HTTP contracts.
- aiogram for Telegram updates and callbacks.
- SQLAlchemy 2.x async APIs and Alembic migrations.
- PostgreSQL as the authoritative database.
- Render Key Value through a Redis-compatible client for jobs, locks and rate limits.
- A mature Python job framework selected through ADR and tested for retry/idempotency behavior.
- web3.py or lower-level Ethereum clients behind project-owned interfaces.
- Pydantic settings with secret references and strict startup validation.
- `pytest`, async test support, PostgreSQL integration tests, and pinned-chain fork tests.
- Ruff/type checking/formatting selected and enforced in CI.
- Docker for repeatable local, CI and Render runtimes.

Dependency versions must be locked. No dependency with signing or serialization responsibility is upgraded without fixture and regression tests.

## 16. Configuration and secrets

Required configuration groups:

- `APP_ENV`
- `DATABASE_URL`
- `QUEUE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_PLATFORM_OWNER_IDS`
- `CHAINSTACK_ETHEREUM_HTTP_URL`
- `CHAINSTACK_ETHEREUM_WSS_URL`
- `ETHEREUM_CHAIN_ID=1`
- `ETHEREUM_REORG_LOOKBACK`
- `INDEXER_INITIAL_CHUNK`
- `INDEXER_MAX_CHUNK`
- `SIGNER_INTERNAL_URL`
- signer service authentication references
- managed KMS/HSM key reference
- `MAX_EXECUTION_WALLETS_PER_WORKSPACE`
- observability and alert destinations

Rules:

- Validate all required settings at startup.
- Refuse to start when chain ID returned by RPC is not 1.
- Never print secret values during validation.
- Use separate bot tokens, databases, queues, RPC credentials and signer keys for development, staging and production.
- Do not store secrets in `render.yaml`, git, Docker images, fixtures or memory logs.

## 17. Delivery phases and acceptance gates

### Phase 0 — Architecture and repository foundation

Tasks:

- [x] Create ADR-001: Ethereum mainnet and Chainstack provider contract.
- [x] Create ADR-002: global intelligence versus workspace-private data.
- [x] Create ADR-003: Telegram approval and revocation model.
- [x] Create ADR-004: signer custody, KMS/HSM and recovery model.
- [x] Create ADR-005: queue/job framework.
- [x] Create ADR-006: paper simulation method and evidence standard.
- [x] Scaffold repository and module boundaries.
- [x] Add Dockerfile and local development composition.
- [x] Add lint, type-check, unit-test, migration-test and secret-scan CI jobs.
- [x] Add structured logging with mandatory redaction.
- [x] Add configuration validation and environment separation.
- [x] Create initial domain enums from Appendix A of the specification.
- [x] Create fixture manifest for required historical transactions.

Exit gate:

- [x] ADRs are accepted.
- [x] CI passes from a clean clone.
- [x] Application starts without production secrets in test mode.
- [x] Secret scan and log-redaction tests pass.
- [x] No signing or broadcasting dependency is reachable.

Clean-clone verification passed against pushed commit `6377493` on the locked toolchain.

### Phase 1 — Access control and tenant isolation

Tasks:

- [x] Add access, user, workspace, membership, challenge and audit migrations.
- [x] Implement `RequestContext` and authorization middleware.
- [x] Implement `/start` access requests.
- [x] Implement owner approval, rejection and revocation callbacks.
- [x] Create the personal workspace and default strategy atomically on approval.
- [x] Add private-chat enforcement.
- [x] Add Telegram update deduplication.
- [x] Add challenge TTL, single-use and replay protection.
- [x] Add repository-level workspace scoping.
- [x] Add PostgreSQL row-level security where selected by ADR.
- [x] Add per-user/workspace rate limiting.
- [x] Add unauthorized-attempt alerts.

Exit gate:

- [x] Two-user isolation suite proves no cross-user reads or writes.
- [x] Duplicate `/start` and webhook deliveries have one effect.
- [x] Forwarded or replayed callbacks fail.
- [x] Group-chat privileged commands fail.
- [x] Revoked users lose access immediately.
- [x] Audit events identify actor, action, result and correlation ID.

Phase 1 completed in GitHub Actions run `31047635556` for commit `9ea2ff3`. Both migration stacks,
the non-superuser PostgreSQL isolation suite, secret scan, dependency audit, and production
container build passed.

### Phase 2 — Wallet creation without transaction execution

Tasks:

- [x] Implement signer private-service skeleton.
- [x] Integrate the selected managed KMS/HSM.
- [x] Implement idempotent Ethereum key creation.
- [x] Store encrypted signer material separately from application records.
- [x] Add execution-wallet migration and repository.
- [x] Implement `/create_wallet` confirmation.
- [x] Implement `/wallets` and balance refresh.
- [x] Enforce configurable per-workspace wallet limits.
- [x] Add signer health reporting.
- [x] Add backup and restore runbook.
- [x] Complete a non-production key restore drill.
- [x] Keep signing and broadcasting endpoints disabled.

Exit gate:

- [x] A user sees only their own wallet addresses.
- [x] Repeated creation requests return the same result.
- [x] No key plaintext appears in DB, Telegram, logs, traces or error output.
- [x] Restored key derives the expected address.
- [x] Signer refuses a cross-workspace key reference.
- [x] Custody/recovery notice is owner-approved; legal review remains a launch gate.

Implementation is active. Unit and HTTP boundary tests cover envelope encryption, exact address
recovery, authenticated/replay-protected signer calls, idempotency, wallet limits, Telegram
confirmation, and a hard-locked signing endpoint. PostgreSQL isolation suites and both migration
stacks pass in GitHub Actions and against separate local Docker PostgreSQL services. The remaining
technical gate passed using a real non-production AWS KMS key and an isolated PostgreSQL
backup/restore copy; evidence is recorded in
`docs/runbooks/evidence/2026-08-05-signer-restore-drill.md`. The custody notice is owner-approved;
legal review remains required before users may fund wallets.

### Phase 3 — Historical Ethereum intelligence

Tasks:

- [x] Add chain, collection, scan, evidence and mint-event migrations.
- [x] Implement Chainstack provider interface and startup chain-ID check.
- [x] Implement collection validation with `eth_getCode`.
- [x] Implement deployment-block resolver and confidence metadata.
- [x] Implement proxy metadata history.
- [x] Implement ERC-721 decoder.
- [x] Implement ERC-1155 single/batch decoder.
- [x] Implement ERC-2309 decoder and range policy.
- [x] Implement adaptive block scanner.
- [x] Make event persistence and checkpoint advancement atomic.
- [x] Add transaction, receipt and trace enrichment.
- [x] Implement identity roles, confidence and reason codes.
- [ ] Implement mint route and classification reason codes.
- [x] Add `/add_collection`, `/scan` and `/collections`.
- [ ] Add progress and quality-warning notifications.

Development provider evidence on 2026-08-06 confirms chain ID, safe/finalized tags,
historical code, bounded logs, transaction/receipt reads, and WSS subscriptions. The endpoint
accepts 10-block log ranges but rejects 50-block ranges with HTTP 403, so scanning shrinks this
response adaptively. `debug_traceTransaction` is HTTP 403 and remains an external capability gate
for trace-dependent enrichment and paper simulation; see
`docs/runbooks/evidence/2026-08-06-chainstack-capability.md`.

Exit gate:

- [ ] Golden fixture counts match expected mint events.
- [ ] Worker termination resumes without missing or duplicating events.
- [x] ERC-1155 batch sub-index keys are deterministic.
- [x] Provider range errors shrink and retry safely.
- [x] Re-scans are idempotent.
- [x] Low-confidence identities are stored as unknown rather than guessed.

### Phase 4 — Overlap analytics and watchlists

Tasks:

- [ ] Add wallet aggregate and score-version migrations.
- [ ] Implement support count.
- [ ] Implement pair, group and at-least-k intersections.
- [ ] Implement Jaccard similarity.
- [ ] Add classification/finality/identity filters.
- [ ] Implement `/overlap`, `/compare` and `/wallet_history`.
- [ ] Add workspace-private watchlists.
- [ ] Implement `/watch` and `/unwatch`.
- [ ] Preserve watch reason and score version.
- [ ] Add pagination and query-performance indexes.

Exit gate:

- [ ] The specification's Collection 1/2/3 overlap scenario passes.
- [ ] Quantity does not inflate distinct collection support.
- [ ] Airdrop/admin/bridge exclusions work by default.
- [ ] Score recalculation preserves earlier versions.
- [ ] User A cannot infer User B's watchlist.
- [ ] Target production-size overlap queries meet the documented latency budget.

### Phase 5 — Live monitoring and opportunities

Tasks:

- [ ] Implement WebSocket new-head listener.
- [ ] Implement HTTPS block catch-up and durable cursor.
- [ ] Add provisional/safe/finalized/reorged transitions.
- [ ] Implement reorg lookback and canonical hash checks.
- [ ] Correlate resolved mint identities with private watchlists.
- [ ] Create deduplicated workspace opportunities.
- [ ] Add opportunity expiry and aggregated reason handling.
- [ ] Implement Telegram opportunity cards.
- [ ] Add `/opportunities`.
- [ ] Add lag, reconnect, duplicate and reorg metrics.

Exit gate:

- [ ] Dropped WebSocket messages are recovered by cursor catch-up.
- [ ] Duplicate source events create one opportunity per workspace.
- [ ] A reorg expires dependent opportunities and reverses derived state.
- [ ] Spam recipient-only mints do not become high-confidence intent by default.
- [ ] Cross-workspace opportunity visibility tests pass.
- [ ] Event-to-opportunity latency meets the configured MVP target.

### Phase 6 — Direct and SeaDrop paper mode

Tasks:

- [ ] Define typed adapter results and reason codes.
- [ ] Implement direct-public recognition and sale inspection.
- [ ] Implement direct-public eligibility, quote and build.
- [ ] Implement SeaDrop public recognition and sale inspection.
- [ ] Implement SeaDrop public eligibility, quote and build.
- [ ] Reject allowlist, signed and token-gated phases without independent eligibility.
- [ ] Implement gas estimation and worst-case total.
- [ ] Implement provider-backed simulation and inconclusive state.
- [ ] Verify expected interactions/effects according to ADR-006.
- [ ] Persist immutable paper plans and evidence.
- [ ] Implement `/paper`, `/strategy` and `/mode alert|paper`.
- [ ] Add explicit paper-only Telegram copy.

Exit gate:

- [ ] Direct paid/free public-mint fixtures pass.
- [ ] SeaDrop public fixture passes.
- [ ] SeaDrop allowlist and signed fixtures are rejected for an ineligible wallet.
- [ ] Source-wallet calldata, proofs and signatures are never copied.
- [ ] Sold-out, changed-price, wrong-chain and insufficient-evidence cases fail safely.
- [ ] No signing or broadcast call can occur from any Release 1 route.
- [ ] End-to-end test passes from access approval through paper report.

### Phase 7 — Production hardening and invite-only launch

Tasks:

- [ ] Create production Render environment and Blueprint.
- [ ] Provision paid PostgreSQL with backups/PITR appropriate to the selected plan.
- [ ] Provision persistent Render Key Value with a no-eviction policy suitable for queues.
- [ ] Deploy bot API, workers and private signer separately.
- [ ] Configure separate Chainstack production endpoints.
- [ ] Configure Telegram webhook and secret header.
- [ ] Restrict datastore public access and use private connection strings.
- [ ] Run migrations as a controlled pre-deploy action.
- [ ] Add service health, readiness and dependency checks.
- [ ] Configure metrics, alerts and redacted error reporting.
- [ ] Test backup restoration.
- [ ] Test RPC outage, Redis loss, worker restart and signer outage runbooks.
- [ ] Run dependency, container, secret and permission scans.
- [ ] Approve the first invite list.

Exit gate:

- [ ] Staging end-to-end and chaos suites pass.
- [ ] Database restoration is demonstrated.
- [ ] Signer restoration is demonstrated without key exposure.
- [ ] Platform pause works while read-only intelligence remains available.
- [ ] Unauthorized Telegram and callback-replay alerts are active.
- [ ] Production contains no manual/auto execution capability.
- [ ] Owner signs the Release 1 launch checklist.

## 18. Testing matrix

| Layer | Required coverage |
|---|---|
| Unit | Decoders, address normalization, policies, reason codes, amount arithmetic and state transitions. |
| Database | Constraints, migrations, atomic checkpoints, tenant scoping and concurrent jobs. |
| Isolation | Two or more users across commands, callbacks, APIs, workers, repositories and signer references. |
| Historical fixtures | Raw transactions, receipts, logs and traces for every supported standard and route. |
| Provider contract | Chainstack range behavior, timeouts, WebSocket reconnects, finality tags and trace availability. |
| Fork | Quote/build/simulation against pinned Ethereum state. |
| Telegram | Access approval, update dedupe, private-chat checks, callback expiry/replay and redaction. |
| Signer | Creation idempotency, encryption, recovery, wrong workspace/chain and disabled signing. |
| End-to-end | Unknown user through approval; collection through overlap; watched mint through paper plan. |
| Chaos | Worker kill, RPC outage, queue restart, DB reconnect and source reorg. |
| Security | Dependency, secret, container, permission, log-redaction and threat-model regression tests. |

Minimum golden fixtures:

- ERC-721 direct paid public mint;
- ERC-721 free public mint;
- gift mint where initiator differs from recipient;
- ERC-1155 single and batch mint;
- ERC-2309 consecutive mint;
- SeaDrop public mint;
- SeaDrop allowlist rejection;
- SeaDrop signed-mint rejection;
- admin airdrop;
- bridge/migration mint;
- lazy marketplace mint;
- ERC-4337/bundler transaction;
- unknown relayer;
- reorganized log.

## 19. Security verification checklist

- [ ] Telegram bot token rotation documented.
- [ ] Webhook secret checked before update parsing.
- [ ] Platform owner uses numeric Telegram ID.
- [ ] All privileged commands are private-chat-only.
- [ ] Callback values are opaque and server-reloaded.
- [ ] Database contains no plaintext private keys.
- [ ] Logs redact RPC URLs, tokens, key material and sensitive payloads.
- [ ] Signer has no public endpoint.
- [ ] Signer caller authentication is enforced.
- [ ] Workspace key-reference isolation is tested.
- [ ] KMS/HSM access follows least privilege.
- [ ] Application and signer backups are encrypted.
- [ ] Restore drills are documented.
- [ ] Release 1 cannot sign or broadcast.
- [ ] Malicious/unknown contracts remain alert-only.
- [ ] Dependency and container scans run in CI.
- [ ] Production shell and secret access are limited to platform administrators.

## 20. Observability and operations

Required metrics:

- indexer head, finalized lag, scan cursor, chunk size, log count, retries and provider errors;
- WebSocket connection status, reconnect count and catch-up depth;
- decoded events by standard, route, classification and confidence;
- overlap latency and watchlist correlation count;
- opportunities by workspace-safe aggregate, route and decision;
- paper quote/build/simulation latency and rejection reasons;
- queue depth, job age, retry count and dead-letter count;
- signer health and wallet-creation failures without key data;
- Telegram webhook failures, duplicates, unauthorized attempts and expired callbacks.

Required runbooks:

- Chainstack outage or inconsistent block hash;
- WebSocket disconnection and catch-up;
- indexer stuck or provider range failure;
- Ethereum reorganization;
- PostgreSQL outage and restore;
- Render Key Value loss;
- signer outage and encrypted restore;
- Telegram token compromise;
- accidental secret exposure;
- platform-wide pause;
- user revocation;
- wallet recovery request.

## 21. Render deployment rules

- Use a Render web service only for public Telegram/API traffic.
- Use background workers for continuous queue-consuming processes.
- Use a private service for the signer because it must accept only internal requests.
- Use managed PostgreSQL and Key Value; do not use service-local files as durable state.
- Keep development, staging and production in separate protected environments.
- Use internal datastore URLs and block unnecessary public access.
- Apply database migrations once per release through a controlled pre-deploy step.
- Give workers graceful shutdown time to finish or safely abandon bounded jobs.
- Production must not use expiring/free PostgreSQL or non-persistent queue plans.
- `render.yaml` contains topology and non-secret configuration only.

## 22. Release 2 preparation — not active in Release 1

Do not implement or enable these as shortcuts during Release 1. Before manual execution, add:

- independent application and signer policy versions;
- maximum mint price, gas, total and daily limits;
- atomic commitments for approved and pending spend;
- typed signer authorization envelope;
- one nonce lock namespace per chain and wallet;
- durable nonce reservation before signing;
- exact-plan Telegram approval with 60–120 second expiry;
- signed-hash persistence and unknown-broadcast reconciliation;
- replacement transactions using the same nonce;
- receipt, finality, failure, drop, replacement and reorg states;
- kill switch tested against an in-flight attempt;
- low-value staging and production drills;
- external security review.

## 23. Open decisions and blockers

The following decisions are intentionally not guessed. They must be resolved through ADRs before their dependent gates:

- [x] Managed KMS/HSM provider for signer encryption/custody: AWS KMS envelope encryption.
- [x] User recovery/export policy outside Telegram: account recovery and encrypted keystore export
  after separate identity verification; never deliver key material through Telegram.
- [x] Maximum execution wallets per workspace: configurable, with a beta default of one.
- [ ] Exact Chainstack plan with archive and debug/trace access.
- [ ] Secondary/failover Ethereum RPC provider for production resilience.
- [ ] Render region and production instance sizes.
- [x] Job queue framework: Celery with Render Key Value/Redis transport.
- [ ] Simulation evidence method available through the selected Chainstack node.
- [ ] Historical trace retention policy and storage cost ceiling.
- [ ] Initial invitation volume and per-user scan quotas.
- [x] Custody notice is shown before wallet creation; legal review remains required before funding.

None of these blocks repository foundation or read-only intelligence work. KMS/recovery blocks production wallet creation; trace/simulation capability blocks paper-mode completion.

## 24. Work-tracking protocol

For every implementation task:

1. Select the earliest unchecked task whose dependencies are complete.
2. Record the relevant requirement, threat, and acceptance test in the pull request or change description.
3. Write or update the failing test before or with the implementation.
4. Implement behind the defined interface.
5. Run the narrow tests, then the full phase suite.
6. Update documentation, runbooks and migrations in the same change.
7. Check the task only after its evidence exists.
8. Do not check a phase exit gate until every listed condition is demonstrated.
9. Append the completed work and next step to `.memory/MEMORY_LOG.md` at session end, following `Rules.md`.

Phase status vocabulary:

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED` — must include the blocking decision or external dependency
- `VERIFYING`
- `COMPLETE`

Current status:

| Phase | Status |
|---|---|
| Phase 0 — Foundation | `COMPLETE` |
| Phase 1 — Access and isolation | `COMPLETE` |
| Phase 2 — Wallet creation | `COMPLETE` |
| Phase 3 — Historical intelligence | `IN_PROGRESS` |
| Phase 4 — Analytics | `NOT_STARTED` |
| Phase 5 — Live monitoring | `NOT_STARTED` |
| Phase 6 — Paper mode | `NOT_STARTED` |
| Phase 7 — Launch hardening | `NOT_STARTED` |

## 25. Release 1 definition of done

Release 1 is complete only when:

- an unknown Telegram user can request access and cannot use protected commands;
- the platform owner can approve, reject and revoke access securely;
- approval creates a private workspace;
- users cannot access one another's private records or execution wallets;
- the signer creates an Ethereum address without exposing key material;
- a user can add an Ethereum collection and receive a reproducible mint dataset;
- scans resume without gaps or duplicates;
- overlap analytics find repeated minters dynamically across all stored collections;
- a private watchlist produces reorg-aware live alerts;
- supported public direct and SeaDrop mints produce fresh paper plans;
- ineligible, unknown, allowlisted, signed and gated routes fail closed with explanations;
- every paper result clearly states that nothing was signed or broadcast;
- no production code path can sign or broadcast;
- backups, restore drills, monitoring, alerts, pause controls and incident runbooks pass;
- Critical and High edge cases applicable to Release 1 have regression coverage;
- the platform owner approves the final launch checklist.

## 26. Validated platform references

- Chainstack Ethereum `eth_getLogs`: https://docs.chainstack.com/reference/ethereum-getlogs
- Chainstack node modes and archive/debug availability: https://docs.chainstack.com/docs/protocols-modes-and-types
- Chainstack Ethereum debug and trace methods: https://docs.chainstack.com/reference/ethereum-debug-trace-rpc-methods
- Render service types: https://render.com/docs/service-types
- Render private services: https://render.com/docs/private-services
- Render background workers: https://render.com/docs/background-workers
- Render Blueprint specification: https://render.com/docs/blueprint-spec
- Render deployment and ephemeral-filesystem behavior: https://render.com/docs/deploys
