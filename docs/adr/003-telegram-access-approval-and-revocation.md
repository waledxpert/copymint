# ADR-003: Telegram access approval, authorization and revocation

- Status: Accepted
- Date: 2026-08-05
- Owners: Product owner, bot engineering, security

## Context

The product is free but invite-only. The preferred onboarding flow lets a person start the bot and request access, after which the platform owner approves or rejects them. Telegram usernames are mutable, forwarded messages are untrusted, callbacks can be replayed, and webhook updates can be delivered more than once.

## Decision

The immutable Telegram numeric user ID is the external identity key. Usernames and display names are non-authoritative metadata.

Unknown users may invoke only `/start`, `/help`, and `/access_status` in a private chat. `/start` creates or returns one active access request. It does not create a workspace.

The platform owner is identified by a non-empty configured list of numeric Telegram user IDs. The owner receives an approval card with an opaque request ID and single-use approve/reject challenges.

Approval atomically creates:

- an active platform user;
- a personal workspace;
- a `workspace_owner` membership;
- a default alert-only strategy;
- a notification destination for the private chat;
- access-decision and workspace-creation audit events.

Rejection records an optional reason and cooldown. Revocation immediately denies new commands and jobs, invalidates outstanding challenges, and records the actor/reason. Historical audit and public chain evidence remain intact.

## Request and callback rules

- Privileged commands are refused outside private chats.
- Telegram's webhook secret header is checked before parsing the update.
- `(bot_id, update_id)` is durably unique.
- Callback data contains only an opaque challenge token and a protocol version.
- The stored challenge binds action, expected actor, private chat, resource, authoritative values, expiry, and consumed state.
- Challenges expire quickly and are consumed atomically.
- A forwarded approval message cannot authorize its recipient.
- Authorization middleware produces an immutable `RequestContext`; handlers never construct one from callback values.
- Error messages do not reveal whether another user's resource exists.

## Roles in Release 1

- `platform_owner`: access decisions, adapter administration, platform pause, health.
- `workspace_owner`: only their personal workspace and paper-mode resources.
- `service_worker`: bounded background work; no membership or policy administration.
- `signer`: key custody operations; no Telegram access authority.

## Consequences

- Joining the bot is simple but never self-authorizing.
- Owner approval is an operational bottleneck acceptable for the invite-only beta.
- Access decisions and retries are explainable and idempotent.
- Team invitations and delegated workspace roles are deferred without blocking the personal-workspace data model.

## Rejected alternatives

- Username allowlists: rejected because usernames can change.
- Secret invite code as the only control: rejected because codes can be forwarded.
- Automatic approval on `/start`: rejected because the owner chose explicit approval.
- Privileged group-chat commands: rejected because membership and forwarded-message semantics increase exposure.
- Trusting callback payload fields: rejected because clients can replay or tamper with payloads.

## Verification

- Duplicate `/start` calls yield one active request.
- Duplicate webhook updates have one effect.
- Wrong-user, wrong-chat, expired, consumed, and forwarded callbacks fail.
- Revocation blocks access immediately, including queued workspace jobs at execution time.
- Telegram username changes do not alter authorization.
- Unauthorized attempts generate rate-limited security audit events.
