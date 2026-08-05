# ADR-005: Celery, Render Key Value and idempotent jobs

- Status: Accepted
- Date: 2026-08-05
- Owners: Backend engineering, operations

## Context

Historical scans, live catch-up, analytics, opportunity creation, and paper planning are long-running or retryable work that must not execute in Telegram's webhook request path. Render supplies continuously running background workers and a Redis-compatible Key Value service. Queue delivery can be duplicated or interrupted, and Redis cannot be the authoritative record of blockchain or execution state.

## Decision

Use Celery 5.x with Render Key Value as broker. PostgreSQL remains authoritative for job intent, progress, checkpoints, idempotency, outcomes, and audit history. The Celery result backend is not business truth.

Use named queues:

- `indexer`
- `live`
- `analytics`
- `opportunities`
- `maintenance`

Tasks use at-least-once delivery. Correctness comes from database uniqueness, explicit idempotency keys, transactional checkpoints, and state-machine guards—not an exactly-once claim.

Default worker posture:

- acknowledge after bounded work completes;
- reject/requeue on worker loss where safe;
- prefetch one task for long/blockchain jobs;
- set explicit soft and hard time limits;
- use exponential backoff with jitter for classified transient errors;
- cap attempts and persist terminal failure details in PostgreSQL;
- revalidate workspace access and resource state at execution time;
- carry correlation ID and idempotency key in headers and job rows.

Tasks must be bounded. A historical scan task processes one block range, commits events and checkpoint, and enqueues the next range. It does not hold one queue message for an entire collection history.

Celery Beat is not required in the initial skeleton. Periodic reconciliation may later use one explicitly singleton scheduler or Render cron jobs. Running multiple accidental schedulers is prohibited.

## Redis/Key Value policy

- Use a persistent paid plan in production.
- Configure `noeviction` for queue correctness.
- Separate logical prefixes by environment and purpose.
- Store only ephemeral locks, rate-limit counters, challenges, and queue messages.
- Never store private keys or authoritative audit/state data.
- Size the visibility timeout beyond the maximum allowed bounded task time.

Loss of Key Value pauses new paper/execution work. Workers reconcile PostgreSQL job state and durable chain cursors before resuming. Release 2 transaction execution will have stricter Redis-loss gates.

## Idempotency contract

Each mutating job has:

- stable task type;
- caller-generated or server-derived idempotency key;
- immutable resource identity;
- optional workspace ID;
- attempt number;
- correlation ID;
- durable PostgreSQL state.

The worker acquires/creates the durable job record before side effects. A retry loads and resumes that record. Database constraints arbitrate duplicate workers; Redis locks reduce contention but are not the final correctness boundary.

## Consequences

- Telegram responses stay fast while work continues asynchronously.
- Duplicate queue delivery is expected and tested.
- PostgreSQL load increases because progress and idempotency are durable.
- Celery's synchronous worker model remains isolated from async application code through small task adapters.
- Queue loss is recoverable from durable intent/cursors, but causes an operational pause.

## Rejected alternatives

- In-process background tasks: rejected because deploys/restarts lose work.
- Redis as job source of truth: rejected because queue state is not sufficient for audit or recovery.
- Claiming exactly-once queue delivery: rejected as technically misleading.
- One task per full collection backfill: rejected because it is difficult to retry, time-bound, and observe.
- Unbounded automatic retries: rejected because provider/configuration failures can create retry storms.

## Verification

- Deliver the same task twice concurrently and observe one durable side effect.
- Kill a worker before and after database commit and verify safe resume.
- Restart Key Value and reconcile durable pending jobs/cursors.
- Verify revoked workspaces cannot execute an older queued private job.
- Verify correlation/idempotency metadata appears in redacted structured logs.

## References

- https://render.com/docs/background-workers
- https://render.com/docs/service-types
- https://render.com/docs/blueprint-spec
- https://docs.celeryq.dev/
