# Memory Log
> Append-only. Never delete or edit previous entries.
> Initialized: 2026-08-05

---

## 2026-08-05 — Phase 0 architecture and repository foundation

### Project Status & Decisions
- Implemented Phase 0 from `implementation.md` and changed its status from `NOT_STARTED` to `VERIFYING`.
- Added and accepted ADR-001 through ADR-006 covering Ethereum/Chainstack, global versus workspace-private data, Telegram approval/revocation, AWS KMS signer custody/recovery, Celery job semantics, and paper simulation evidence.
- Initialized a local Git repository. No commit or remote has been created yet.
- Locked Release 1 at paper mode in code; signing and broadcasting return unavailable/locked and cannot be raised through environment configuration.
- Kept the clean-clone CI exit gate unchecked because a GitHub remote and first Actions run do not exist yet; all local CI-equivalent checks pass.

### Tech Stack & Tools
- Pinned Python 3.13.13 and uv 0.11.6 with 125 resolved packages in `uv.lock`.
- Scaffolded FastAPI bot/API and private signer services, Celery/Render Key Value workers, SQLAlchemy/Alembic, PostgreSQL, structured JSON logging, central redaction, Docker, Compose, and `render.yaml`.
- Added process-specific settings so the API receives no Chainstack/KMS secrets, blockchain workers receive no Telegram/KMS secrets, and the signer receives no Telegram/Chainstack secrets.
- Added GitHub Actions checks for formatting, lint, strict typing, tests, PostgreSQL migration smoke test, secret scan, dependency audit, and production-container build.
- Created the 15-case Ethereum golden-fixture manifest in `tests/fixtures/manifest.json`.

### Problems Solved / Lessons Learned
- [Current dependency advisories]: `pip-audit` found five fixable vulnerabilities in `cryptography 46.0.7` and `pytest 8.4.2`; constraints and lockfile were updated to `cryptography 50.0.0` and `pytest 9.1.1`, after which the audit reported no known vulnerabilities.
- [Secret leakage across services]: Replaced one all-secrets settings object with API, worker, signer, and database-specific settings classes.
- [False simulation certainty]: Defined verified, partial, inconclusive, and failed evidence levels; `eth_call` success alone is not treated as proof of a mint.
- [Queue exactly-once misconception]: Adopted at-least-once Celery delivery with PostgreSQL idempotency and bounded tasks.
- [Sandbox Git ownership]: Git commands in this environment require a per-command `safe.directory` override; no global Git configuration was changed.

### Goals & Next Steps
- Create the first Git commit, connect the intended GitHub repository, and run GitHub Actions from a clean clone to close the final Phase 0 exit gate.
- After that gate passes, change Phase 0 to `COMPLETE` and begin Phase 1 access-control and tenant-isolation migrations.
- Obtain real development-only Telegram, Chainstack, Render, and AWS KMS configuration through secret stores; never place them in source or memory.

---

## 2026-08-05 — CopyMint specification review and implementation baseline

### Project Status & Decisions
- Read and reviewed `NFT_Mint_Intelligence_Copy_Mint_Technical_Specification.docx`, including its seven embedded architecture/workflow diagrams.
- Created `implementation.md` as the working implementation source of truth with 8 delivery phases, 175 checklist items, acceptance gates, testing, security, operations, and Release 1 definition of done.
- Locked Release 1 to invite/owner-approved Telegram access, Ethereum mainnet, Chainstack RPC, Render hosting, free invite-only use, private personal workspaces, signer-created per-user wallets, live alerts, and paper mode.
- Real transaction signing, broadcasting, manual copy, and automatic copy are excluded from Release 1 and remain later security-gated releases.
- Split shared global on-chain intelligence from workspace-private wallets, watchlists, strategies, opportunities, plans, notifications, and audit records.

### Tech Stack & Tools
- Planned Python, FastAPI, aiogram, SQLAlchemy/Alembic, PostgreSQL, Render Key Value, Chainstack Ethereum HTTPS/WSS, isolated signer, managed KMS/HSM, pytest, Docker, and Render services.
- Validated Chainstack Ethereum log, archive, and debug/trace capabilities against official documentation; exact paid plan remains an ADR decision.
- Validated Render web, background worker, private service, PostgreSQL, Key Value, Blueprint, pre-deploy, and ephemeral-filesystem behavior against official documentation.

### Problems Solved / Lessons Learned
- [Single-team assumptions in the specification]: Added a multi-user workspace/access model and mandatory tenant scoping so unrelated invited users cannot see or operate one another's resources.
- [Duplicate blockchain work across users]: Kept immutable public Ethereum observations global while making user intent and custody records private.
- [Custodial wallet risk]: Made KMS/HSM selection, encrypted recovery, restore drills, custody notice, and signer isolation production wallet-creation gates.
- [First release financial risk]: Capped Release 1 at paper mode and required signing/broadcasting paths to be unavailable.
- [Free product versus hosting]: Documented that user access is free, while production Render workers, private signer, database, and persistent queue require paid infrastructure.

### Goals & Next Steps
- Begin Phase 0 in `implementation.md`: create the six architecture decision records, scaffold the repository, establish CI, configuration validation, structured redaction, and the golden-fixture manifest.
- Resolve the KMS/HSM provider, out-of-band wallet recovery policy, Chainstack plan, failover RPC, Render region/sizing, job framework, simulation method, and initial user quotas before their dependent release gates.

---

## 2026-08-05 — Phase 1 access control and tenant isolation implementation

### Project Status & Decisions
- Confirmed the Phase 0 commit `6377493` was pushed to `https://github.com/waledxpert/copymint.git`; clean-clone checks passed and Phase 0 moved to `COMPLETE`.
- Implemented all Phase 1 tasks and moved Phase 1 to `VERIFYING`; its remaining gates require the PostgreSQL service in GitHub Actions.
- Kept onboarding free and invite-only: unknown users request access with `/start`, and configured platform owners approve, reject, or revoke through actor-bound confirmation callbacks.
- Approval atomically creates an active platform user, private personal workspace, owner membership, Telegram destination, and default alert-only strategy.

### Tech Stack & Tools
- Added SQLAlchemy models and Alembic migration `0001_phase1_access_control.py` for users, requests, workspaces, memberships, destinations, strategies, callback challenges, Telegram updates, and audit logs.
- Added PostgreSQL row-level security, repository scoping, UUIDv7 identifiers, durable Telegram update deduplication with failed-update retry, and Redis fixed-window limits per user and workspace.
- Wired aiogram handlers and middleware into an authenticated FastAPI `/telegram/webhook` boundary with constant-time secret comparison and no raw update logging.
- Added PostgreSQL-backed CI tests plus unit/API tests for access, private-chat enforcement, challenge replay/actor binding, callbacks, webhook deduplication, authorization auditing, and rate limiting.

### Problems Solved / Lessons Learned
- [Duplicate webhook retry trap]: Changed the PostgreSQL claim upsert so processed updates remain deduplicated while failed dispatches can be reclaimed safely.
- [Callback tampering and forwarding]: Stored only SHA-256 token hashes and bound every short-lived, single-use challenge to the expected action, Telegram actor, chat, and authoritative server-side payload.
- [Tenant leakage]: Added repository context setters and forced PostgreSQL RLS policies; integration tests cover cross-workspace reads and writes.
- [False security alerts during onboarding]: Unauthorized attempts are audited and logged for protected actions while `/start`, `/access_status`, and `/help` are excluded.
- [Test secret false positive]: Replaced a realistic literal Telegram test token with a runtime-constructed value; the 97-file secret scan then passed.

### Goals & Next Steps
- Push the Phase 1 batch and let GitHub Actions run migration smoke tests and the four PostgreSQL integration cases: two-user isolation, revocation, audit completeness, and atomic challenge/update behavior.
- If CI passes, mark the remaining Phase 1 exit gates complete and change Phase 1 to `COMPLETE`.
- Begin Phase 2 only after that gate, focusing on KMS-backed per-user Ethereum wallet creation with no signing or broadcasting route exposed.

---

## 2026-08-05 — GitHub Actions migration failure fix

### Project Status & Decisions
- Investigated failed public GitHub Actions run `31043490194` for commit `a5e46ea`; formatting, lint, and typing passed, while the `Migration smoke test` failed.
- Kept Phase 1 in `VERIFYING` until the corrected migration and PostgreSQL integration suite pass in GitHub Actions.

### Tech Stack & Tools
- Used the public GitHub Actions REST API to isolate the failed job and step.
- Corrected Alembic RLS generation and updated CI to separate the PostgreSQL migration administrator from the non-superuser application test role.
- Added a regression assertion for the workspace RLS tenant-key mapping.

### Problems Solved / Lessons Learned
- [Migration undefined column]: `enable_workspace_rls()` assumed every table had `workspace_id`; the `workspaces` table uses `id`, so its policy now explicitly uses `workspace_column="id"`.
- [Misleading isolation test]: The original CI connection used the PostgreSQL service superuser, which bypasses RLS even with `FORCE ROW LEVEL SECURITY`; migrations now run as `copymint_admin` and integration tests run as `copymint_app NOSUPERUSER`.

### Goals & Next Steps
- Commit and push the three-file CI fix, then inspect the next GitHub Actions run.
- If the PostgreSQL integration tests pass, close all remaining Phase 1 exit gates and begin Phase 2.

---

## 2026-08-05 — Phase 2 encrypted wallet creation

### Project Status & Decisions
- Moved Phase 2 to `IN_PROGRESS` and implemented its signer, application wallet, Telegram, balance-refresh, deployment, and test foundations without enabling transaction execution.
- Selected AWS KMS envelope encryption with AES-256-GCM; the application database stores only the checksummed Ethereum address and opaque `signer_key_id`, while a separate signer database stores encrypted envelopes.
- Kept the per-workspace wallet limit configurable with a beta default of one and kept `/v1/sign` hard-locked with HTTP 423 in Release 1.
- Fixed the still-failing Phase 1 GitHub test by making the API settings test explicitly set `app_env="local"` instead of depending on CI's `APP_ENV=test`.

### Tech Stack & Tools
- Added secp256k1 key generation, AWS KMS data-key generation/decryption, AES-256-GCM authenticated encryption, HMAC-authenticated internal signer requests, durable request-replay claims, and non-production restore verification.
- Added independent signer SQLAlchemy metadata, Alembic configuration/migration, Render private-service pre-deploy migration, and separate signer credentials.
- Added workspace-RLS execution-wallet records, idempotent creation, `/create_wallet`, `/wallets`, exact integer wei formatting, and Celery/Chainstack balance refresh pinned to an Ethereum mainnet block.
- Added signer, wallet, Telegram, KMS, HTTP-client, Ethereum RPC, migration, credential-isolation, and PostgreSQL integration tests.

### Problems Solved / Lessons Learned
- [CI environment-dependent unit test]: Explicitly supplied the expected app environment in the settings test so GitHub's `APP_ENV=test` no longer changes the assertion.
- [Custodial key exposure]: Bound ciphertext to environment, workspace, chain, address, signer key ID, and purpose through AES-GCM additional authenticated data; no key plaintext is stored in either database.
- [Cross-user wallet leakage]: Applied forced PostgreSQL RLS and mandatory repository workspace context to every wallet read and mutation.
- [RPC secret separation]: The API only publishes opaque workspace/wallet refresh jobs; only the worker has the Chainstack endpoint.
- [Stale asynchronous balances]: Persisted the observed block number and rejected updates older than the latest stored snapshot.

### Goals & Next Steps
- Push this batch and let GitHub Actions run both migration stacks and all seven PostgreSQL integration cases as non-superuser roles.
- Complete a real non-production AWS KMS plus restored-signer-database drill using `docs/runbooks/signer-backup-and-restore.md`.
- Review and approve `docs/custody-and-recovery-notice.md`; define the out-of-band recovery/export policy before production wallets may be funded.
- After CI evidence passes, close the remaining Phase 1 and eligible Phase 2 exit gates in `implementation.md`.

---

## 2026-08-05 — Green CI and local Docker isolation verification

### Project Status & Decisions
- Confirmed pushed commit `9ea2ff3` and GitHub Actions run `31047635556` completed successfully across formatting, lint, typing, both migrations, non-superuser tests, secret scanning, dependency auditing, and the production container build.
- Closed every Phase 1 exit gate and changed Phase 1 from `VERIFYING` to `COMPLETE` in `implementation.md`.
- Kept Phase 2 `IN_PROGRESS`; its remaining external gates are a real non-production AWS KMS/database restore drill and owner approval of the custody/recovery notice.

### Tech Stack & Tools
- Used Docker Desktop 4.85.0 / Engine 29.6.2 to run PostgreSQL 16 Alpine and Redis 7 Alpine locally.
- Split local application and signer persistence into physically separate PostgreSQL services, volumes, databases, credentials, and host ports in `compose.yaml`.
- Ran both Alembic stacks and all PostgreSQL-backed tests locally with non-superuser runtime roles.
- Added cross-platform selector-loop handling for Windows Alembic/pytest async psycopg connections.

### Problems Solved / Lessons Learned
- [Docker executable missing from inherited PATH]: Located the per-user Docker Desktop installation and temporarily added its `resources/bin` directory so the CLI and credential helper could run.
- [Local signer isolation mismatch]: Replaced the shared local PostgreSQL database with a dedicated `signer-postgres` service on port 5433 and its own persistent volume.
- [Windows psycopg failure]: The default Proactor loop caused `Psycopg cannot use the 'ProactorEventLoop'`; Alembic and pytest now select `asyncio.SelectorEventLoop` on Windows.
- [Isolation test assumed one PostgreSQL host]: Updated the negative signer-connection test to combine application credentials with the configured signer host/database, so it works with both CI's logical separation and Docker's physical separation.

### Goals & Next Steps
- Push the local Docker/Windows portability batch and verify the next GitHub Actions run remains green.
- Provision a non-production AWS KMS key and isolated signer database, then execute and record the restore drill from `docs/runbooks/signer-backup-and-restore.md`.
- Obtain owner approval of `docs/custody-and-recovery-notice.md` and decide the out-of-band recovery/export policy before allowing wallet funding.

---

## 2026-08-05 — Recovery policy approval and live KMS drill attempt

### Project Status & Decisions
- Recorded owner approval of the custody notice and selected two future out-of-band options: account recovery and encrypted Ethereum keystore export.
- Kept both recovery operations disabled during the paper release; Telegram may never carry private keys, keystore files, passwords, KMS payloads, or recovery download links.
- Attempted the first live non-production AWS KMS drill. AWS credentials loaded correctly, but the configured IAM identity was denied `kms:DescribeKey` on the selected test key, so the restore gate remains open.

### Tech Stack & Tools
- Added `docs/wallet-recovery-and-export-policy.md` with identity verification, two-person export approval, signer-only processing, encrypted expiring artifacts, separate password delivery, audit, and incident-pause controls.
- Added `scripts/signer_restore_drill.py` for repeatable KMS health, wallet creation, idempotency, address restoration, and cross-workspace rejection checks.
- Added signer-only static AWS credential settings so ignored local `.env` credentials are passed explicitly to boto3 while remaining absent from API and worker settings.
- Added sanitized KMS exception handling and regression coverage so AWS account, identity, key ARN, and provider messages do not escape through service errors.

### Problems Solved / Lessons Learned
- [Local `.env` credentials not visible to boto3]: Pydantic read the file, but boto3's provider chain did not; signer settings now pass an optional complete access-key pair explicitly.
- [AWS exception metadata exposure]: Raw `ClientError` text included account and key identifiers; `KmsOperationError` now retains only the safe provider error code and suppresses the original exception chain.
- [Incomplete drill permissions]: The IAM/key policies must allow `kms:DescribeKey`, `kms:GenerateDataKey`, and `kms:Decrypt` for exactly the non-production key.

### Goals & Next Steps
- Grant the dedicated drill IAM identity the three scoped KMS actions and ensure the KMS key policy permits that identity.
- Rerun `scripts/signer_restore_drill.py create`, restore the signer database backup into isolation, and run its `verify` command against the restored copy.
- Push this policy, drill tooling, and KMS error-sanitization batch after the full quality suite remains green.

---

## 2026-08-05 — Phase 2 restore gate completed

### Project Status & Decisions
- Confirmed the owner added the scoped AWS KMS permissions and successfully reran the real non-production drill.
- Marked every Phase 2 task and exit gate complete and changed Phase 2 to `COMPLETE` in `implementation.md`.
- Retained legal review as a launch/funding gate; no signing, broadcasting, recovery, or export capability was enabled.

### Tech Stack & Tools
- Generated an unfunded Ethereum drill wallet using a real AWS KMS data key, verified creation idempotency, restored the exact address, and rejected a wrong workspace.
- Created a custom-format PostgreSQL signer backup, restored it into the isolated temporary `copymint_signer_restore_drill` database, and verified the exact address again using AWS KMS.
- Verified application credentials could not enter the restored signer database and reviewed only schema column names for absence of a plaintext private-key field.
- Recorded sanitized drill evidence in `docs/runbooks/evidence/2026-08-05-signer-restore-drill.md`.

### Problems Solved / Lessons Learned
- [Incomplete IAM permissions]: Adding key-scoped `kms:DescribeKey`, `kms:GenerateDataKey`, and `kms:Decrypt` allowed the complete live KMS round trip.
- [Restore evidence needed a negative test]: Extended the drill verifier to reject a random wrong workspace against the restored database as well as the source database.
- [Disposable custody artifacts]: Removed the exact temporary restored database, backup file, and unfunded source drill envelope after evidence capture; counts verified all three were gone.

### Goals & Next Steps
- Push the Phase 2 completion evidence and enhanced drill verifier, then confirm GitHub Actions remains green.
- Begin Phase 3 with Ethereum chain, collection, scan, evidence, and mint-event migrations plus the Chainstack provider contract.

---

## 2026-08-06 — Phase 3 Ethereum intelligence foundation

### Project Status & Decisions
- Confirmed GitHub Actions run `31054947241` passed for Phase 2 completion commit `abb38af`.
- Began Phase 3 and moved it to `IN_PROGRESS`; completed the foundational schema, collection validation, deployment resolution, standard mint decoders, and adaptive range planner.
- Preserved global on-chain data as shared immutable evidence rather than workspace-owned data.

### Tech Stack & Tools
- Added migration `6014276fbd67_phase3_ethereum_intelligence_foundation.py` and SQLAlchemy models for chains, collections, proxy implementation intervals, scan jobs/checkpoints, chain cursors, raw evidence, and mint events.
- Seeded Ethereum mainnet as EIP-155 chain ID 1 and enforced event provenance, confidence, quantity, address normalization, and idempotency constraints.
- Added a PostgreSQL trigger that rejects updates or deletes of raw evidence.
- Added a credential-safe JSON-RPC provider, mainnet verification, `eth_getCode` collection validation, finalized deployment-block binary search, and classified range errors.
- Added strict ERC-721, ERC-1155 single/batch, and bounded ERC-2309 decoders with deterministic batch/range sub-indexes.
- Added an adaptive scanner that shrinks provider-rejected ranges and commits successful ranges without gaps.

### Problems Solved / Lessons Learned
- [Alembic autogenerate false positives]: Removed unrelated legacy check-constraint drops/recreations from the generated migration before validation.
- [Draft migration downgrade]: Made the raw-evidence function drop tolerant of a local database that had applied the pre-trigger draft, then passed a complete downgrade/upgrade cycle.
- [Provider credential leakage]: Provider errors expose only classified codes and never include the configured Chainstack URL.
- [Unbounded ERC-2309 expansion]: Added a configurable maximum range and explicit rejection instead of risking uncontrolled row generation.

### Goals & Next Steps
- Add atomic raw-evidence/mint-event persistence with checkpoint advancement and idempotent re-scan behavior.
- Implement transaction, receipt, and trace enrichment plus conservative identity/route/classification reason codes.
- Add proxy implementation discovery and workspace-private collection registration with `/add_collection`, `/scan`, and `/collections`.
- Obtain development Chainstack HTTPS/WSS endpoints to run the live provider capability gate and populate reviewed golden fixtures.

---

Continuation: atomic batch persistence was completed in the same session after this entry was
written. `SqlAlchemyMintBatchConsumer` now inserts immutable raw log evidence, idempotent decoded
mint events, and the monotonic scan checkpoint in one PostgreSQL transaction. Replaying the same
batch produces one evidence row, one mint event, and one checkpoint; the full suite passed with 86
tests and 83.42% coverage.

---

## 2026-08-06 — Live Chainstack range and enrichment capability verification

### Project Status & Decisions
- Verified the configured development Chainstack HTTPS/WSS credentials without recording either endpoint or credential.
- Confirmed chain ID 1, safe/finalized tags, historical contract code, 10-block log retrieval, finalized transaction/receipt reads, and WSS new-head subscribe/unsubscribe behavior.
- Kept trace-dependent enrichment and paper simulation gated because `debug_traceTransaction` returned sanitized HTTP 403.

### Tech Stack & Tools
- Added `scripts/chainstack_capability_probe.py` with process-minimal `EthereumProviderSettings`, sanitized validation/provider failures, and a partial-result exit when trace is unavailable.
- Hardened `JsonRpcEvmProvider` so an `eth_getLogs` HTTP 403 is classified as a transient splittable-range response; the adaptive scanner can reduce the request until accepted.
- Recorded the live, credential-free capability result in `docs/runbooks/evidence/2026-08-06-chainstack-capability.md` and linked it from Phase 3 in `implementation.md`.

### Problems Solved / Lessons Learned
- [Probe unnecessarily required DB and Redis]: Introduced focused provider settings so the diagnostic needs only Chainstack HTTP/WSS values and chain ID.
- [Documented versus effective log range]: The endpoint accepted one-block and 10-block ranges but rejected 50, 99, 100, and 1,001 blocks with HTTP 403; range sizing must remain adaptive.
- [Trace method unavailable]: Transaction and receipt calls passed, while `debug_traceTransaction` returned HTTP 403; a compatible paid/global Chainstack node or equivalent trace-capable provider is required for that gate.

### Goals & Next Steps
- Enable debug/trace access on a compatible development Chainstack deployment, then rerun the capability probe.
- Complete trace-aware identity, route, and classification persistence while preserving unknown values whenever evidence is missing.
- Add proxy implementation history and workspace-private `/add_collection`, `/scan`, and `/collections` flows.

---

## 2026-08-06 — Private collection commands and resumable scan worker

### Project Status & Decisions
- Completed the Phase 3 EIP-1967 proxy implementation-history resolver and marked the proxy-history task complete.
- Added workspace-private `/add_collection`, `/scan`, and `/collections` flows; the same global Ethereum collection can be shared without exposing either workspace's private label or subscription.
- Kept all Chainstack credentials in the worker. The API publishes only an opaque global collection UUID to the indexer queue.

### Tech Stack & Tools
- Added migration `0003_workspace_collections.py`, the `WorkspaceCollection` model, forced PostgreSQL RLS, repository scoping, audit creation, and a two-user isolation test.
- Added `Eip1967ImplementationResolver` using the standardized implementation storage slot, verified `Upgraded` logs, implementation bytecode checks, and finalized-storage reconciliation.
- Added `copymint.ethereum.scan_collection`, which validates collections and processes fixed historical ranges in resumable 100-block slices while the adaptive scanner shrinks provider-rejected requests.
- Wired collection services, Celery publishing, Telegram handlers, API composition, and worker imports.

### Problems Solved / Lessons Learned
- [Global intelligence versus private product state]: Deduplicated the chain/address globally while placing labels, active state, actor, and notification settings behind workspace RLS.
- [API RPC-secret boundary]: Collection commands never receive a Chainstack endpoint; only the worker validates code and scans Ethereum.
- [Provider range restrictions]: Each durable scan slice still uses adaptive subranges, so the observed 10-block endpoint limit does not create checkpoint gaps.

### Goals & Next Steps
- Add progress and quality-warning notifications for collection scans.
- Persist transaction/receipt enrichment and conservative identity, route, and classification reasons; keep trace-derived roles unknown until debug/trace access is enabled.
- Add worker kill/resume evidence and reviewed historical golden fixtures before closing Phase 3 exit gates.

---
