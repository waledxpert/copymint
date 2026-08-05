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
